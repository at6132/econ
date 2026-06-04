"""Profile solo process startup the way realm_solo.py does (menu routes only)."""
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.setdefault("REALM_SOLO_MODE", "1")
os.environ.setdefault("REALM_LLM_DISABLE", "1")

t0 = time.perf_counter()


def mark(label: str, since: float) -> float:
    now = time.perf_counter()
    print(f"{label}: {now - since:.2f}s")
    return now


t = time.perf_counter()
t = mark("start", t)
t1 = time.perf_counter()
from realm.api.socket_server import warm_http_stack, _dispatch  # noqa: E402

mark("import socket_server", t1)
t1 = time.perf_counter()
warm_http_stack()
mark("warm_http_stack()", t1)
t1 = time.perf_counter()
ver = _dispatch("GET", "/version", {})
mark("dispatch /version", t1)
print("build_id", ver.get("build_id"))
t1 = time.perf_counter()
lst = _dispatch("GET", "/persistence/list", {})
mark("dispatch /persistence/list", t1)
print("slots", len(lst.get("slots", [])))
mark("TOTAL (menu path)", t0)
