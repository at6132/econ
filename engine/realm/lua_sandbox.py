"""Gated Lua execution (dev) — ``REALM_LUA_EVAL=1`` and ``lupa`` required.

User chunks run under a minimal ``setfenv`` sandbox (Lua 5.1 style). Not a security boundary for
untrusted internet input; solo / local dev gate only.
"""

from __future__ import annotations

import os
import re
from typing import Any

MAX_EVAL_BYTES = 8192

# Patterns matched case-insensitively against the whole source.
_FORBIDDEN_RE = re.compile(
    r"\b(?:require|dofile|loadfile|loadstring|io\.|os\.|debug|package|coroutine|"
    r"getfenv|setfenv|string\.dump|collectgarbage|newproxy|module)\b",
    re.IGNORECASE,
)

# Lua 5.1 runner: loadstring + setfenv; ``tick``, ``purpose``, stripped ``math``.
_LUA_RUNNER = r"""
return function(user_src, tick_val, purpose_val)
  local _ENV = {
    tick = tick_val,
    purpose = purpose_val,
    math = {
      abs = math.abs,
      floor = math.floor,
      min = math.min,
      max = math.max,
      sqrt = math.sqrt,
    },
  }
  local f, err = loadstring(user_src)
  if not f then
    return false, tostring(err)
  end
  setfenv(f, _ENV)
  local ok, r = pcall(f)
  if not ok then
    return false, tostring(r)
  end
  return true, r
end
"""


def eval_user_lua_chunk(
    source: str,
    *,
    tick: int,
    purpose: str,
) -> dict[str, Any]:
    """
    Run ``source`` as a Lua chunk returning one value (or nil).

    Requires ``os.environ["REALM_LUA_EVAL"] == "1"`` and optional dependency ``lupa``.
    """
    if os.environ.get("REALM_LUA_EVAL") != "1":
        return {"ok": False, "reason": "set REALM_LUA_EVAL=1 to enable (local dev only)"}
    if not isinstance(source, str):
        return {"ok": False, "reason": "source must be a string"}
    raw = source.encode("utf-8")
    if len(raw) > MAX_EVAL_BYTES:
        return {"ok": False, "reason": f"source exceeds {MAX_EVAL_BYTES} bytes"}
    if _FORBIDDEN_RE.search(source):
        return {"ok": False, "reason": "source matched forbidden pattern (io/os/require/…)"}
    try:
        import lupa  # type: ignore[import-untyped]
    except ImportError:
        return {"ok": False, "reason": "lupa not installed (pip install -e .[lua])"}

    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    runner = rt.eval(_LUA_RUNNER)
    ok, res = runner(source, int(tick), str(purpose))
    if not ok:
        return {"ok": False, "reason": str(res)}
    return {"ok": True, "result": res}
