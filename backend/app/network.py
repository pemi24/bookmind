"""This computer's addresses on the local network, for opening BookMind from a phone or another device."""
from __future__ import annotations

import ipaddress
import socket

import segno


def lan_addresses() -> list[str]:
    """IPv4 addresses other devices on the network can reach; the main Wi-Fi/Ethernet one first."""
    found: list[str] = []
    try:
        # No packet is sent: connecting a UDP socket just picks the interface that reaches the network.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    return [ip for ip in found if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback]


def reachable_from_network(host: str) -> bool:
    """Whether the server listens on all interfaces (LAN mode) rather than only on this computer."""
    return host in ("0.0.0.0", "::", "")


def qr_svg(url: str) -> str:
    """A QR code for the address, as inline SVG (scan it with the phone's camera)."""
    return segno.make(url, error="m").svg_inline(scale=5, border=2, dark="#1c1917", light="#ffffff")
