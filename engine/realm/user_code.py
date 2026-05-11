"""User-code layer (Primitive 9) — HTTP contract for Phase 4; sandbox not wired yet.

See ``realm_docs/07_USER_CODE_LAYER.md``. All future Lua/services execution routes through
engine actions (transaction layer); no direct state mutation.
"""

from __future__ import annotations

from typing import Any


def code_layer_public_status() -> dict[str, Any]:
    """Public capability advertisement for clients (solo UI, CLI, future IDE)."""
    return {
        "phase": "stub",
        "lua_runtime": False,
        "docs_path": "realm_docs/07_USER_CODE_LAYER.md",
        "message": (
            "Deterministic Lua sandbox and deploy pipeline are Phase 4; "
            "the engine API already exposes the same actions scripts will call."
        ),
    }
