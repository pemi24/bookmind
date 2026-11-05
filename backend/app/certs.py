"""A certificate for the optional HTTPS phone mode (HTTPS=true), made on this computer.

Phones only treat BookMind as a secure site (offline app shell, fewer media restrictions) over
HTTPS. There is no public domain to get a real certificate for, so BookMind makes its own small
certificate authority (CA) once, and with it a server certificate for this computer's names and
network addresses. Each phone trusts the CA once (README, "On your phone"); the server
certificate is re-issued by the same CA whenever the computer's addresses change or it nears
expiry, so phones never need to trust it again.

Files live in HTTPS_DIR (backend/data/https). ca.key never leaves this computer; ca.crt is the
public part phones download. To use your own certificate instead (e.g. made with mkcert), set
SSL_CERTFILE / SSL_KEYFILE (and SSL_CA_FILE for the download link).
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_DAYS = 3650
# Apple rejects TLS certificates valid for more than 825 days, and browsers are moving to ~398.
SERVER_DAYS = 397
RENEW_BEFORE = timedelta(days=30)


@dataclass
class CertPaths:
    certfile: Path
    keyfile: Path
    cafile: Path | None  # what phones download and trust; None if unknown (own certificate)


def default_names() -> list[str]:
    """Names this computer answers to besides its IP addresses."""
    names = ["localhost"]
    host = socket.gethostname().strip()
    if host:
        names += [host, f"{host}.local"]
    return names


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _load(cert_path: Path, key_path: Path):
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        return cert, key
    except (OSError, ValueError):
        return None, None


def _ensure_ca(folder: Path) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    cert_path, key_path = folder / "ca.crt", folder / "ca.key"
    cert, key = _load(cert_path, key_path)
    now = datetime.now(timezone.utc)
    if cert is not None and cert.not_valid_after_utc - now > RENEW_BEFORE:
        return cert, key
    key = _key()
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "BookMind (local)"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"BookMind local CA ({socket.gethostname() or 'this computer'})"),
    ])
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(key_path, key)
    _write_cert(cert_path, cert)
    return cert, key


def _san_entries(names: list[str], ips: list[str]) -> list[x509.GeneralName]:
    entries: list[x509.GeneralName] = [x509.DNSName(n) for n in dict.fromkeys(names) if n]
    for ip in dict.fromkeys(["127.0.0.1", "::1", *ips]):
        entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
    return entries


def _covers(cert: x509.Certificate, names: list[str], ips: list[str]) -> bool:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    have_ips = {str(a) for a in san.get_values_for_type(x509.IPAddress)}
    have_names = {n.lower() for n in san.get_values_for_type(x509.DNSName)}
    return set(ips) <= have_ips and {n.lower() for n in names if n} <= have_names


def _issued_by(cert: x509.Certificate, ca: x509.Certificate) -> bool:
    try:
        cert.verify_directly_issued_by(ca)
        return True
    except Exception:  # wrong issuer (ValueError/TypeError) or a bad signature (InvalidSignature)
        return False


def ensure_certificates(folder: Path, ips: list[str], names: list[str] | None = None) -> CertPaths:
    """Create (or refresh) the local CA and a server certificate covering these addresses."""
    names = default_names() if names is None else names
    folder.mkdir(parents=True, exist_ok=True)
    ca_cert, ca_key = _ensure_ca(folder)
    cert_path, key_path = folder / "server.crt", folder / "server.key"
    cert, _ = _load(cert_path, key_path)
    now = datetime.now(timezone.utc)
    fresh = (cert is not None and cert.not_valid_after_utc - now > RENEW_BEFORE
             and _covers(cert, names, ips) and _issued_by(cert, ca_cert))
    if not fresh:
        key = _key()
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0] if names else "localhost")]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=SERVER_DAYS))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName(_san_entries(names, ips)), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        _write_key(key_path, key)
        _write_cert(cert_path, cert)
    return CertPaths(cert_path, key_path, folder / "ca.crt")


def resolve(settings, ips: list[str] | None = None, create: bool = True) -> CertPaths | None:
    """The certificate HTTPS mode serves: the configured one, else BookMind's own (made if needed)."""
    if settings.ssl_certfile and settings.ssl_keyfile:
        ca = Path(settings.ssl_ca_file) if settings.ssl_ca_file else None
        return CertPaths(Path(settings.ssl_certfile), Path(settings.ssl_keyfile), ca)
    folder = Path(settings.https_dir)
    if create:
        from app.network import lan_addresses
        return ensure_certificates(folder, lan_addresses() if ips is None else ips)
    if (folder / "server.crt").is_file() and (folder / "ca.crt").is_file():
        return CertPaths(folder / "server.crt", folder / "server.key", folder / "ca.crt")
    return None


def ca_fingerprint(cafile: Path) -> str:
    """SHA-256 fingerprint of the CA, to compare with what the phone shows before trusting it."""
    cert = x509.load_pem_x509_certificate(cafile.read_bytes())
    return ":".join(f"{b:02X}" for b in cert.fingerprint(hashes.SHA256()))
