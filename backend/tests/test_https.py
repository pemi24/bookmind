"""Optional HTTPS phone mode: the local CA and server certificate, the CA download and /api/network."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from cryptography import x509

from app import certs
from tests.conftest import signed_in


def _san(path):
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return cert, {str(i) for i in san.get_values_for_type(x509.IPAddress)}, set(san.get_values_for_type(x509.DNSName))


def test_certificate_covers_this_computer_and_is_signed_by_the_ca(tmp_path):
    paths = certs.ensure_certificates(tmp_path, ["192.168.1.20"], ["localhost", "reader-pc", "reader-pc.local"])
    cert, ips, names = _san(paths.certfile)
    ca = x509.load_pem_x509_certificate(paths.cafile.read_bytes())
    assert {"192.168.1.20", "127.0.0.1", "::1"} <= ips
    assert {"localhost", "reader-pc", "reader-pc.local"} <= names
    cert.verify_directly_issued_by(ca)
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    # Apple refuses TLS certificates valid for more than 825 days.
    assert (cert.not_valid_after_utc - datetime.now(timezone.utc)).days <= 825


def test_new_address_reissues_the_server_certificate_with_the_same_ca(tmp_path):
    first = certs.ensure_certificates(tmp_path, ["192.168.1.20"], ["localhost"])
    ca_before, server_before = first.cafile.read_bytes(), first.certfile.read_bytes()

    certs.ensure_certificates(tmp_path, ["192.168.1.20"], ["localhost"])  # nothing changed: kept
    assert first.certfile.read_bytes() == server_before

    again = certs.ensure_certificates(tmp_path, ["10.0.0.7"], ["localhost"])  # Wi-Fi gave a new address
    assert again.cafile.read_bytes() == ca_before  # phones don't need to trust anything new
    assert again.certfile.read_bytes() != server_before
    _, ips, _ = _san(again.certfile)
    assert "10.0.0.7" in ips


def test_own_certificate_files_are_used_as_given(tmp_path):
    class S:
        ssl_certfile, ssl_keyfile, ssl_ca_file, https_dir = "c.pem", "k.pem", "", tmp_path

    paths = certs.resolve(S())
    assert str(paths.certfile) == "c.pem" and str(paths.keyfile) == "k.pem" and paths.cafile is None
    assert not any(tmp_path.iterdir())  # BookMind made nothing of its own


def test_fingerprint_is_sha256_hex(tmp_path):
    paths = certs.ensure_certificates(tmp_path, [], ["localhost"])
    fp = certs.ca_fingerprint(paths.cafile)
    assert len(fp.split(":")) == 32


@pytest.fixture
def https_on(tmp_path, monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "https", True)
    monkeypatch.setattr(s, "https_dir", tmp_path)
    monkeypatch.setattr(s, "host", "0.0.0.0")
    monkeypatch.setattr("app.network.lan_addresses", lambda: ["192.168.1.20"])
    certs.ensure_certificates(tmp_path, ["192.168.1.20"])
    return s


@pytest.mark.asyncio(loop_scope="session")
async def test_ca_download_only_in_https_mode(test_db, tmp_path, monkeypatch):
    import httpx

    from app.config import get_settings
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/bookmind-ca.crt")).status_code == 404  # off by default

        s = get_settings()
        monkeypatch.setattr(s, "https", True)
        monkeypatch.setattr(s, "https_dir", tmp_path)
        made = certs.ensure_certificates(tmp_path, ["192.168.1.20"])
        r = await c.get("/bookmind-ca.crt")  # no sign-in needed: it's the public half
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-x509-ca-cert")
        assert r.content == made.cafile.read_bytes()
        assert b"PRIVATE KEY" not in r.content


@pytest.mark.asyncio(loop_scope="session")
async def test_network_lists_secure_addresses(test_db, https_on):
    from app.main import app

    async with signed_in(app) as c:
        info = (await c.get("/api/network")).json()
    # Opened as http://test, so that address (and its https twin) comes first, then this computer's.
    p, sp = https_on.port, https_on.https_port
    assert [a["url"] for a in info["addresses"]] == [f"http://test:{p}", f"http://192.168.1.20:{p}"]
    assert info["https"]["enabled"] is True
    assert [a["url"] for a in info["https"]["addresses"]] == [f"https://test:{sp}", f"https://192.168.1.20:{sp}"]
    assert "<svg" in info["https"]["addresses"][0]["qr_svg"]
    # The certificate is fetched over plain http, before the phone trusts the https address.
    assert info["https"]["ca_url"] == f"http://test:{p}/bookmind-ca.crt"
    assert len(info["https"]["ca_fingerprint"].split(":")) == 32


@pytest.mark.asyncio(loop_scope="session")
async def test_network_without_https_is_unchanged(test_db):
    from app.main import app

    async with signed_in(app) as c:
        info = (await c.get("/api/network")).json()
    assert info["https"]["enabled"] is False and info["https"]["addresses"] == []
    assert all(a["url"].startswith("http://") for a in info["addresses"])

