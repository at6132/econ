"""Solo socket server dispatches through the same FastAPI routes as HTTP."""

from __future__ import annotations

import json
import socket
import threading
import time

from realm.api.socket_server import _dispatch, run


def test_dispatch_health_without_world() -> None:
    out = _dispatch("GET", "/health", {})
    assert out.get("status") == "ok"


def test_dispatch_dev_reset_frontier() -> None:
    out = _dispatch("POST", "/dev/reset?seed=1&scenario=frontier", {})
    assert out.get("ok") is True
    tick = _dispatch("POST", "/tick", {})
    assert tick.get("ok") is True
    assert int(tick.get("tick", 0)) >= 1


def test_dispatch_persistence_save_and_list() -> None:
    _dispatch("POST", "/dev/reset?seed=1&scenario=frontier", {})
    saved = _dispatch("POST", "/persistence/save?slot=socket_test", {})
    assert saved.get("ok") is True
    assert "saves/" in str(saved.get("path", ""))
    listed = _dispatch("GET", "/persistence/list", {})
    assert listed.get("ok") is True
    paths = [str(s.get("path", "")) for s in listed.get("slots", [])]
    assert any("socket_test" in p for p in paths)


def test_tcp_line_protocol() -> None:
    host, port = "127.0.0.1", 19001
    thread = threading.Thread(target=run, kwargs={"host": host, "port": port}, daemon=True)
    thread.start()
    deadline = time.time() + 5.0
    sock: socket.socket | None = None
    while time.time() < deadline:
        try:
            sock = socket.socket()
            sock.connect((host, port))
            break
        except OSError:
            time.sleep(0.05)
    assert sock is not None
    req = json.dumps({"id": "1", "method": "GET", "path": "/health", "body": {}}) + "\n"
    sock.sendall(req.encode())
    sock.settimeout(2.0)
    buf = ""
    resp: dict | None = None
    deadline = time.time() + 3.0
    while time.time() < deadline and resp is None:
        try:
            chunk = sock.recv(4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk.decode()
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if parsed.get("id") == "1":
                resp = parsed
                break
    sock.close()
    assert resp is not None
    assert resp.get("status") == "ok"
