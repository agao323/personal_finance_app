#!/usr/bin/env python3
"""Prove server-sent events cross the proxy as they are written: `make smoke` runs this.

Reads `/api/advisor/stream-check` through web — which the API answers with three heartbeats
a second apart — and fails unless the first arrives within 1.5 s and they arrive spread out,
not all at once. It asks for gzip, as a browser does, because a compressing hop that buffers
is the failure this exists to catch.

Standard library only, so it runs on the host with no environment to set up.
"""

from __future__ import annotations

import sys
import time
import urllib.request
import zlib

FIRST_WITHIN = 1.5
MIN_SPREAD = 1.5  # three events one second apart span about two seconds


def main(url: str) -> int:
    request = urllib.request.Request(
        url, headers={"Accept": "text/event-stream", "Accept-Encoding": "gzip"}
    )
    started = time.monotonic()
    arrivals: list[float] = []
    with urllib.request.urlopen(request, timeout=10) as response:
        encoding = response.headers.get("Content-Encoding", "")
        inflate = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
        buffered = b""
        while True:
            chunk = response.read1(4096)
            if not chunk:
                break
            buffered += inflate.decompress(chunk) if inflate else chunk
            while b"\n\n" in buffered:
                event, buffered = buffered.split(b"\n\n", 1)
                if event.startswith(b"data: "):
                    arrivals.append(time.monotonic() - started)
    shown = ", ".join(f"{t:.2f}s" for t in arrivals)
    if len(arrivals) != 3:
        print(f"  FAIL: expected 3 heartbeats, got {len(arrivals)} ({shown})", file=sys.stderr)
        return 1
    if arrivals[0] > FIRST_WITHIN:
        print(f"  FAIL: first heartbeat at {arrivals[0]:.2f}s — something buffers", file=sys.stderr)
        return 1
    if arrivals[-1] - arrivals[0] < MIN_SPREAD:
        print(f"  FAIL: heartbeats arrived together ({shown}) — buffered", file=sys.stderr)
        return 1
    print(f"  ok: heartbeats at {shown}{' (gzip)' if inflate else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
