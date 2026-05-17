#!/usr/bin/env python3
"""
Entry point for Realm solo mode.
Godot spawns this as a child process.
Writes REALM_READY:<host>:<port> to stdout when the TCP listener is up.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
os.environ.setdefault("REALM_LLM_DISABLE", "1")

from realm.api.socket_server import run

if __name__ == "__main__":
    port = int(os.environ.get("REALM_TCP_PORT", "9000"))
    run(port=port)
