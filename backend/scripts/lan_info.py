"""Print the address to open BookMind from a phone on the same Wi-Fi (used by start.bat lan / start.sh --lan)."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402


def lan_addresses() -> list[str]:
    found: list[str] = []
    try:
        # No packet is sent: connecting a UDP socket just picks the interface used to reach the network.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def main() -> None:
    port = get_settings().port
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
    print(" Then: iPhone (Safari) Share > Add to Home Screen;  Android (Chrome) menu > Add to Home screen.")
    print(" Only use this on a network you trust (e.g. home Wi-Fi): anyone on it can open")
    print(" your library. If the phone can't connect, allow Python through the firewall")
    print(" for private networks.")
    print(line)


if __name__ == "__main__":
    main()
