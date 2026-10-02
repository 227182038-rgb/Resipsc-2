#!/usr/bin/env python3
"""supervisor.py — server auto-restart daemon.

Watches the Next.js standalone server; restarts it if the process dies or the
health endpoint fails N consecutive checks. Never exits; logs to stderr.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

CHECK_INTERVAL = 15
MAX_FAILS = 3


def is_alive(port: int = 3000) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://localhost:{port}/", timeout=10) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_server() -> subprocess.Popen:
    env = dict(os.environ)
    env.setdefault("PORT", "3000")
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=2048")
    proc = subprocess.Popen(
        ["node", "server.js"],
        cwd=os.path.join(os.getcwd(), ".next", "standalone"),
        env=env,
        stdout=open("server.log", "ab"),
        stderr=subprocess.STDOUT,
    )
    print(f"[supervisor] server started pid={proc.pid}", file=sys.stderr)
    return proc


def main() -> int:
    fails = 0
    proc = None
    while True:
        alive = is_alive()
        if not alive:
            fails += 1
            print(f"[supervisor] health check failed ({fails}/{MAX_FAILS})", file=sys.stderr)
            if fails >= MAX_FAILS:
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                proc = start_server()
                fails = 0
                time.sleep(20)
                continue
        else:
            fails = 0
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
