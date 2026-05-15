"""Solo client WebSocket — Godot ``WS.gd`` connects to ``/ws`` for optional live pushes.

No game logic here. Accepts connections and reads client frames until disconnect so logs stay quiet.
Broadcast helpers can notify subscribers after ticks (optional — extend ``broadcast_json``).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket

router = APIRouter()

# Connected peers (solo/dev scale — acceptable set growth during sessions).
_clients: set[WebSocket] = set()


async def broadcast_json(payload: dict[str, Any]) -> None:
    """Best-effort push to all open `/ws` clients (ignored failures)."""
    if not _clients:
        return
    raw = json.dumps(payload)
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_text(raw)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@router.websocket("/ws")
async def solo_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
    except Exception:
        pass
    finally:
        _clients.discard(websocket)
