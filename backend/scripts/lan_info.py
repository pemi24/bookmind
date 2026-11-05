"""Print the address to open BookMind from a phone on the same Wi-Fi (used by start.bat lan / start.sh --lan)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import certs  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.network import lan_addresses  # noqa: E402


def main() -> None:
    s = get_settings()
    port = s.port
    ips = lan_addresses()
    line = "=" * 66
    print(line)
    print(" BookMind is reachable from other devices on this network.")
    if ips:
        print(f"   On your phone, open:  http://{ips[0]}:{port}")
        if len(ips) > 1:  # VPN / virtual machine adapters
            print("   If that doesn't load, try: " + ", ".join(f"http://{ip}:{port}" for ip in ips[1:]))
    else:
        print(f"   Couldn't detect this computer's address; use its Wi-Fi IP and port {port}.")
    if s.https:
        paths = certs.resolve(s, ips)  # made now (or refreshed for new addresses), so it's ready to download
        print(" HTTPS is on (needed for the offline app):")
        if ips:
            print(f"   Secure address:       https://{ips[0]}:{s.https_port}")
            if paths.cafile and paths.cafile.is_file():
                print("   First, on each phone, trust BookMind's certificate (once):")
                print(f"     open  http://{ips[0]}:{port}/bookmind-ca.crt  and follow README > On your phone.")
                print(f"     Its SHA-256 fingerprint starts with {certs.ca_fingerprint(paths.cafile)[:23]}")
        print("   The http:// address keeps working too.")
    print(" Then: iPhone (Safari) Share > Add to Home Screen;  Android (Chrome) menu > Add to Home screen.")
    print(" (In BookMind, the 'Use on your phone' button shows this address as a QR code.)")
    print(" Only use this on a network you trust (e.g. home Wi-Fi): anyone on it can open")
    print(" your library. If the phone can't connect, allow Python through the firewall")
    print(" for private networks.")
    print(line)


if __name__ == "__main__":
    main()
