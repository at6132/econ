"""
Realm solo socket server.

Replaces uvicorn/FastAPI for single-player mode. Listens on a Unix socket
(or TCP localhost on Windows), accepts one persistent connection from Godot,
dispatches JSON requests through the same FastAPI app (in-process TestClient),
and writes JSON responses back.

Protocol (newline-delimited JSON):
  Client → server (request):
    {"id": "1", "method": "GET"|"POST"|"DELETE", "path": "/world/summary", "body": {}}
  Server → client (response, matched by ``id``):
    {"id": "1", "ok": true, ...}
    {"id": "1", "ok": false, "reason": "..."}
  Server → client (PUSH, no ``id``; ``kind`` tells the client what it is):
    {"kind": "tick", "tick": 17, "game_day": 1, "season": "Spring", ...}
    {"kind": "sim_status", "paused": true, "speed": 1.0, ...}

The server runs a background ``sim_loop`` thread that advances the world at
the wall-clock rate ``SimClock`` prescribes (default: 1 game-day = 1 real
hour = 0.4 ticks/s). On each tick the loop pushes a tick frame to every
connected client. Clients can't ask for a tick anymore -- they listen.

The legacy ``POST /tick`` route still works (tests + dev tooling) but is
**no longer the game's metronome**.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_log = logging.getLogger("realm.socket_server")
_req_log = logging.getLogger("realm.socket_server.request")

_test_client: Any | None = None
_test_client_lock = threading.Lock()

# Live connections -- the sim loop pushes tick frames to each.
_connections: set[socket.socket] = set()
_connections_lock = threading.Lock()


def _socket_path() -> str:
    """Unix socket path (env override → default /tmp/realm_solo.sock)."""
    return os.environ.get("REALM_SOCKET_PATH", "/tmp/realm_solo.sock")


def _is_windows() -> bool:
    return sys.platform == "win32"


def _parse_path(path: str) -> tuple[str, dict[str, str]]:
    """Split ``/route?a=1&b=2`` into path and single-value query dict."""
    parsed = urlparse(path if "://" not in path else path.split("://", 1)[-1])
    path_only = parsed.path or "/"
    query: dict[str, str] = {}
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        if values:
            query[key] = values[0]
    return path_only, query


def _get_test_client() -> Any:
    """Lazy singleton TestClient; enters ASGI lifespan once."""
    global _test_client
    if _test_client is not None:
        return _test_client
    with _test_client_lock:
        if _test_client is not None:
            return _test_client
        from fastapi.testclient import TestClient

        from realm.api.app import app

        client = TestClient(app)
        client.__enter__()
        _test_client = client
        return _test_client


def _http_response_to_dict(response: Any) -> dict[str, Any]:
    if response.status_code < 400:
        data = response.json()
        if isinstance(data, dict):
            return data
        return {"ok": True, "data": data}
    try:
        payload = response.json()
    except Exception:
        return {"ok": False, "reason": response.text or f"HTTP {response.status_code}"}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": str(payload)}
    detail = payload.get("detail", payload)
    if isinstance(detail, list):
        detail = "; ".join(str(x) for x in detail)
    return {"ok": False, "reason": str(detail)}


def _dispatch(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """
    Route a request through the FastAPI app (same handlers as multiplayer HTTP).
    Query parameters may appear in ``path`` or in ``body``; body wins on conflict.

    Acquires ``_state.WORLD_LOCK`` so the sim loop can't run ``advance_tick``
    in parallel with a state-mutating request (claim, trade, build, …).
    """
    from realm.api import _state

    path_only, query = _parse_path(path)
    params = {**query, **{k: str(v) for k, v in body.items() if k not in ("params",)}}
    json_body: dict[str, Any] | None = None
    if method in ("POST", "PUT", "PATCH") and body:
        json_body = dict(body)

    client = _get_test_client()
    method_u = method.upper()
    try:
        with _state.WORLD_LOCK:
            if method_u == "GET":
                response = client.get(path_only, params=params)
            elif method_u == "POST":
                if json_body:
                    response = client.post(path_only, params=query, json=json_body)
                else:
                    response = client.post(path_only, params=params)
            elif method_u == "DELETE":
                response = client.delete(path_only, params=params)
            else:
                return {"ok": False, "reason": f"unsupported method {method}"}
    except Exception as exc:
        _log.exception("socket_server dispatch error: %s %s", method, path_only)
        return {"ok": False, "reason": str(exc)}
    return _http_response_to_dict(response)


def _handle_connection(conn: socket.socket) -> None:
    """Handle one persistent Godot connection. Reads newline-delimited JSON requests."""
    _register_connection(conn)
    try:
        buf = b""
        while True:
            try:
                chunk = conn.recv(65536)
            except (ConnectionResetError, BrokenPipeError):
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except json.JSONDecodeError as e:
                    _send(conn, {"id": None, "ok": False, "reason": f"JSON parse: {e}"})
                    continue
                req_id = req.get("id")
                method = str(req.get("method", "GET")).upper()
                req_path = str(req.get("path", "/"))
                req_body = dict(req.get("body") or {})
                if req.get("query"):
                    req_body = {**dict(req["query"]), **req_body}
                try:
                    t0 = time.perf_counter()
                    result = _dispatch(method, req_path, req_body)
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    ok = bool(result.get("ok", True))
                    _req_log.info(
                        "%s %s %.0fms ok=%s",
                        method,
                        req_path,
                        elapsed_ms,
                        ok,
                    )
                    if elapsed_ms > 200:
                        _log.info("socket slow: %s %s took %.0fms", method, req_path, elapsed_ms)
                except Exception as exc:
                    _log.exception("socket_server dispatch error: %s %s", method, req_path)
                    result = {"ok": False, "reason": str(exc)}
                _send(conn, {"id": req_id, **result})
    finally:
        _unregister_connection(conn)
        conn.close()


def _send(conn: socket.socket, data: dict[str, Any]) -> None:
    try:
        conn.sendall((json.dumps(data, default=str) + "\n").encode())
    except (BrokenPipeError, ConnectionResetError):
        pass


# ── Push delivery (sim loop → connections) ───────────────────────────────────


def _push_to_conn(conn: socket.socket, payload: dict[str, Any]) -> None:
    """Send a single un-id'd frame. Used by the sim loop. Drops on dead socket."""
    try:
        conn.sendall((json.dumps(payload, default=str) + "\n").encode())
    except (BrokenPipeError, ConnectionResetError, OSError):
        # The connection handler will discover the close on its next recv.
        pass


def _broadcast_push(payload: dict[str, Any]) -> None:
    """Send ``payload`` to every connected client. Best-effort; survives drops."""
    with _connections_lock:
        targets = list(_connections)
    for c in targets:
        _push_to_conn(c, payload)


def _register_connection(conn: socket.socket) -> None:
    with _connections_lock:
        _connections.add(conn)
    _log.info("sim_loop: client subscribed (%d total)", len(_connections))
    # Send the current sim status immediately so the UI can paint the
    # HUD without waiting for the first tick.
    try:
        from realm.world.sim_clock import get_sim_clock

        _push_to_conn(conn, {"kind": "sim_status", **get_sim_clock().status_dict()})
    except Exception:  # noqa: BLE001
        _log.exception("sim_loop: failed to send initial sim_status")


def _unregister_connection(conn: socket.socket) -> None:
    with _connections_lock:
        _connections.discard(conn)
    _log.info("sim_loop: client unsubscribed (%d remaining)", len(_connections))


def run(host: str = "127.0.0.1", port: int = 9000) -> None:
    """
    Start the solo socket server.

    On Unix: Unix socket in a background thread plus TCP on ``host:port``.
    On Windows: TCP only (Godot connects to ``127.0.0.1:9000``).

    Also boots the **sim loop** so the world advances at the wall-clock rate
    (``SimClock``) while at least one client is connected. The loop runs once
    per process and is idempotent.
    """
    from realm.api import sim_loop
    from realm.api.solo_logging import configure_solo_logging

    log_path = configure_solo_logging()

    # The loop pushes through ``_broadcast_push`` -- nothing happens while
    # no clients are connected, so spawning here is safe.
    sim_loop.subscribe(_broadcast_push)
    sim_loop.start_sim_loop()

    if not _is_windows():
        threading.Thread(target=_run_unix, args=(_socket_path(),), daemon=True).start()
    _run_tcp(host, port, log_path)


def _run_unix(path: str) -> None:
    from pathlib import Path

    sock_path = Path(path)
    sock_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(1)
    _log.info("Realm solo Unix socket listening on %s", path)
    while True:
        conn, _ = server.accept()
        _handle_connection(conn)


def _run_tcp(host: str, port: int, log_path: Path | str) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    _log.info("Realm solo TCP socket listening on %s:%d (log %s)", host, port, log_path)
    print(f"REALM_READY:{host}:{port}", flush=True)
    print(f"REALM_LOG:{log_path}", flush=True)
    while True:
        conn, addr = server.accept()
        _log.info("client connected %s:%d", addr[0], addr[1])
        _handle_connection(conn)
        _log.info("client disconnected %s:%d", addr[0], addr[1])


if __name__ == "__main__":
    port = int(os.environ.get("REALM_TCP_PORT", "9000"))
    run(port=port)
