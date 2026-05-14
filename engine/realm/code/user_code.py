"""User-code layer (Primitive 9) — validation + capability advertisement.

See ``realm_docs/07_USER_CODE_LAYER.md``. Execution sandbox is Phase 4; mutating actions stay on the engine API.
"""

from __future__ import annotations

from typing import Any

from realm.code.lua_runtime import lua_runtime_detail
from realm.code.lua_sandbox import MAX_EVAL_BYTES

MAX_SOURCE_BYTES = 256_000


def validate_user_source(source: str) -> dict[str, Any]:
    """
    Cheap static checks for IDE / deploy pipeline (no execution).

    Returns ``{ ok: true, bytes, lines, chars }`` or ``{ ok: false, reason }``.
    """
    if not isinstance(source, str):
        return {"ok": False, "reason": "source must be a string"}
    raw = source.encode("utf-8")
    if len(raw) > MAX_SOURCE_BYTES:
        return {"ok": False, "reason": f"source exceeds {MAX_SOURCE_BYTES} UTF-8 bytes"}
    line_count = source.count("\n") + (1 if source else 0)
    return {
        "ok": True,
        "bytes": len(raw),
        "lines": line_count,
        "chars": len(source),
    }


def code_layer_public_status() -> dict[str, Any]:
    """Public capability advertisement for clients (solo UI, CLI, future IDE)."""
    lua = lua_runtime_detail()
    return {
        "phase": "stub",
        "lua_runtime": lua["available"],
        "lua": lua,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "eval_requires_env": "REALM_LUA_EVAL=1",
        "eval_max_bytes": MAX_EVAL_BYTES,
        "docs_path": "realm_docs/07_USER_CODE_LAYER.md",
        "message": (
            "Deterministic Lua sandbox and deploy pipeline are Phase 4; "
            "the engine API already exposes the same actions scripts will call."
        ),
    }
