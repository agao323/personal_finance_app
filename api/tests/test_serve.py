"""Tests for the dual-stack listener.

The property under test cost a deploy to find: on Fly, an IPv4-only socket is
unreachable over the private network, and an IPv6-only one fails the platform's
health check. Only a socket accepting both works, and nothing else in the suite
would notice if this regressed.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from app.serve import build_socket


@pytest.fixture
def listener() -> Iterator[socket.socket]:
    sock = build_socket(0)
    yield sock
    sock.close()


def test_binds_ipv6(listener: socket.socket) -> None:
    assert listener.family == socket.AF_INET6


def test_accepts_ipv4_mapped_connections(listener: socket.socket) -> None:
    """The whole point. IPV6_V6ONLY must be off or IPv4 loopback is refused."""
    assert listener.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0


def test_reachable_over_both_families(listener: socket.socket) -> None:
    port = listener.getsockname()[1]

    for host in ("127.0.0.1", "::1"):
        probe = socket.socket(
            socket.AF_INET if host == "127.0.0.1" else socket.AF_INET6, socket.SOCK_STREAM
        )
        probe.settimeout(3)
        try:
            probe.connect((host, port))
        except OSError as error:  # pragma: no cover - a failure here is the bug
            pytest.fail(f"{host} refused: {error}")
        finally:
            probe.close()


def test_is_reusable_so_a_restart_does_not_wait_on_time_wait(
    listener: socket.socket,
) -> None:
    # Truthy, not 1: macOS reports 4 here and Linux reports 1.
    assert listener.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
