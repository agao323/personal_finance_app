"""Production entrypoint: a genuinely dual-stack listener.

Neither obvious bind works on Fly:

- ``--host 0.0.0.0`` is IPv4-only. Fly's private network is IPv6-only, so every peer
  gets ECONNREFUSED while the app looks healthy on its own loopback.
- ``--host ::`` is IPv6-only here — the socket asyncio creates sets ``IPV6_V6ONLY``,
  so ``127.0.0.1`` is refused and Fly's health check (which uses IPv4 loopback)
  reports critical forever. A permanently-critical check gets the machine restarted
  and hides real failures.

Binding the socket here and clearing ``IPV6_V6ONLY`` gives one socket that accepts
both families, which is what both the private network and the health check need.
"""

from __future__ import annotations

import os
import socket

import uvicorn


def build_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # The line this module exists for.
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.bind(("::", port))
    sock.listen(2048)
    return sock


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    sock = build_socket(port)
    uvicorn.Server(uvicorn.Config("app.main:app", fd=sock.fileno())).run()


if __name__ == "__main__":
    main()
