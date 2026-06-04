#!/usr/bin/env python3
"""
Entry point for Realm solo mode.
Godot spawns this as a child process.

Writes REALM_LOG / REALM_HTTP_READY / REALM_READY to stdout when ready.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("REALM_LLM_DISABLE", "1")
# FastAPI lifespan autosave uses asyncio; the solo TCP handler blocks on recv between
# requests so that loop does not tick. socket_server.run() runs a thread autosave instead.
os.environ.setdefault("REALM_SOLO_MODE", "1")

from realm.api.solo_logging import configure_solo_logging
from realm.api.socket_server import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Realm solo TCP engine for Godot")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("REALM_TCP_PORT", "9000")),
        help="TCP port to bind (Godot tries 9000–9003 if this one is stuck)",
    )
    args = parser.parse_args()
    log_path = configure_solo_logging()
    print(f"REALM_LOG:{log_path}", flush=True)
    print(f"REALM_SOLO_PORT:{args.port}", flush=True)
    run(port=args.port)


if __name__ == "__main__":
    main()
