"""Optional Lua interpreter via ``lupa`` — install ``realm-engine[lua]``.

Phase 4 execution sandbox will sit on top of this; the engine does not eval user code here yet.
"""

from __future__ import annotations

from typing import Any

_LUA_IMPORT_ERROR: str | None = None
try:
    import lupa as _lupa_mod  # type: ignore[import-untyped]
except ImportError as e:  # pragma: no cover — exercised when lupa missing
    _lupa_mod = None
    _LUA_IMPORT_ERROR = str(e)


def lua_runtime_available() -> bool:
    return _lupa_mod is not None


def lua_runtime_detail() -> dict[str, Any]:
    return {
        "available": lua_runtime_available(),
        "package": "lupa",
        "import_error": None if lua_runtime_available() else _LUA_IMPORT_ERROR,
    }
