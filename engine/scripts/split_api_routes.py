"""One-shot splitter that carves realm/api/app.py into APIRouter route files.

This script is invoked from ``engine/`` once during the architecture
refactor. It is not part of the runtime engine. After it has produced the
five ``routes_*.py`` files and a thin new ``app.py``, the refactor commit
also adds a ``_state.py`` shared-singletons module and an updated
``__init__.py`` that delegates state lookups through ``_state``.

URL -> bucket mapping (lower-cased prefix tested first):

    /health           -> world
    /world            -> world
    /world/summary    -> world
    /hire/catalog     -> world
    /tick             -> world
    /tick/batch       -> world
    /llm              -> world
    /code             -> world
    /dev              -> dev
    /persistence      -> dev
    /contracts        -> contracts
    /analytics        -> analytics
    /alerts           -> analytics
    /intel            -> analytics
    /tenders          -> analytics
    /market           -> analytics  # signals + routes too
    /bank             -> analytics
    everything else (/plots, /assay, /deep_survey, /hire, /ship, /routes,
       /roads, /plot/harvest, /trade/p2p, /business, /accounts, /buildings)
                      -> actions
"""

from __future__ import annotations

import os
import re
import sys

APP_PATH = "realm/api/app.py"

BUCKETS = ("world", "dev", "contracts", "analytics", "actions")


def _bucket_for_path(url_path: str) -> str:
    p = url_path.lower()
    if p == "/health":
        return "world"
    if p == "/dev" or p.startswith("/dev/"):
        return "dev"
    if p == "/persistence" or p.startswith("/persistence/"):
        return "dev"
    if p == "/contracts" or p.startswith("/contracts/"):
        return "contracts"
    if p == "/analytics" or p.startswith("/analytics/"):
        return "analytics"
    if p == "/alerts" or p.startswith("/alerts/"):
        return "analytics"
    if p == "/intel" or p.startswith("/intel/"):
        return "analytics"
    if p == "/tenders" or p.startswith("/tenders/"):
        return "analytics"
    if p == "/market" or p.startswith("/market/"):
        return "analytics"
    if p == "/bank" or p.startswith("/bank/"):
        return "analytics"
    if p == "/world" or p.startswith("/world/"):
        return "world"
    if p in ("/tick", "/hire/catalog") or p.startswith("/tick/") or p.startswith("/llm/") or p.startswith("/code/"):
        return "world"
    return "actions"


_DECORATOR_RE = re.compile(r'^@app\.(get|post|put|delete|patch)\(\s*"([^"]+)"')


def _split_into_blocks(src: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Return (preamble, [(bucket, decorator_chain, function_body)]) tuples.

    A "block" is a contiguous chunk of leading blank lines + comment lines +
    one or more @app.X decorators + a def/async def + the function body
    (until the next @app block at column 0 or EOF).
    """
    lines = src.split("\n")
    n = len(lines)
    # Find the first line that starts with @app.
    first_route_line = next(
        (i for i, ln in enumerate(lines) if _DECORATOR_RE.match(ln)), n
    )
    preamble = "\n".join(lines[:first_route_line])

    blocks: list[tuple[str, str, str]] = []
    i = first_route_line
    while i < n:
        # Walk back to absorb leading blank/comment lines belonging to this block.
        block_start = i
        # Walk forward to consume all consecutive @app decorator lines.
        decorator_lines: list[str] = []
        url_path = ""
        while i < n and (m := _DECORATOR_RE.match(lines[i])):
            decorator_lines.append(lines[i])
            url_path = url_path or m.group(2)
            i += 1
        # Now we expect a def or async def line (possibly multi-line param list).
        if i >= n:
            break
        # Consume function header (handles multi-line signatures by counting parens).
        body_start = i
        depth = 0
        seen_open = False
        # The function definition continues until we find a top-level line that
        # is either blank-followed-by-@app at column 0 or EOF. Easier: walk until
        # the next line that begins with "@app." at column 0 (with at most a
        # blank line separating).
        while i < n:
            ln = lines[i]
            i += 1
            if i < n and lines[i].startswith("@app."):
                break
            if i < n and lines[i] == "" and i + 1 < n and lines[i + 1].startswith("@app."):
                # We absorb the blank line as part of the previous block.
                break
        if not decorator_lines:
            # We landed in a "ghost" gap (blank lines between two real route
            # blocks). Skip it -- the trailing blank will be appended to the
            # PREVIOUS block when we join, but we don't emit it as its own.
            continue
        block_text = "\n".join(lines[block_start:i])
        bucket = _bucket_for_path(url_path)
        decorator_chain = "\n".join(decorator_lines)
        function_body = "\n".join(lines[body_start:i])
        blocks.append((bucket, decorator_chain, block_text))
    return preamble, blocks


def _rewrite_for_router(block_text: str) -> str:
    """Apply the per-block source rewrites for the router files."""
    out = block_text
    # @app.X(...) -> @router.X(...)
    out = re.sub(r"@app\.(get|post|put|delete|patch)\(", r"@router.\1(", out)
    # global _world -> global None: we move the assignment to use _state.
    out = re.sub(
        r"^(\s*)global _world\s*$",
        r"\1# (was: global _world; mutation now lives on _state.WORLD)",
        out,
        flags=re.MULTILINE,
    )
    # Bare ``_world = X`` reassignments (only happens in /dev/reset) -> _state.WORLD = X.
    out = re.sub(
        r"^(\s*)_world(\s*=\s*)",
        r"\1_state.WORLD\2",
        out,
        flags=re.MULTILINE,
    )
    # Reads of _world -> _state.WORLD (module-level attribute, always current).
    out = re.sub(r"\b_world\b", "_state.WORLD", out)
    # _save_path(...) -> _state._save_path(...)
    out = re.sub(r"\b_save_path\b", "_state._save_path", out)
    return out


_ROUTER_HEADER = '''"""Realm API routes — {desc}.

Routes split out of the original monolithic ``realm.api.app`` for
maintainability. The shared dev singleton ``WORLD`` and helpers live in
``realm.api._state``; reassigning it (via ``POST /dev/reset``) updates
the value seen by every router because Python module attributes are
looked up dynamically.

This file is intentionally limited to dispatch: parse arguments, call an
action function, return its result. No game logic in routes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query

from realm.actions import (
    buy_survey_report,
    cancel_survey_report_listing,
    claim_plot,
    harvest_plot_output_stock,
    hire_catalog_public,
    hire_worker_stub,
    list_survey_report,
    register_business,
    start_production_on_plot,
    survey_plot,
    transfer_survey_report,
)
from realm.api import _state
from realm.api.persistence import load_snapshot, save_snapshot
from realm.code.lua_sandbox import eval_user_lua_chunk
from realm.code.user_code import code_layer_public_status, validate_user_source
from realm.contracts.social import (
    accept_supply_contract,
    fulfill_supply_contract,
    honor_contract_stub,
    propose_contract_stub,
    propose_supply_contract,
)
from realm.contracts.stubs import (
    accept_equity_stub,
    accept_forward_contract,
    accept_loan_contract,
    accept_service_sub,
    deliver_forward_contract,
    propose_equity_stub,
    propose_forward_contract,
    propose_loan_contract,
    propose_service_sub,
    repay_loan_contract,
)
from realm.core.ids import MaterialId, PartyId, PlotId
from realm.economy.analytics import purchase_analytics_product
from realm.economy.intel import purchase_market_intel
from realm.economy.markets import (
    cancel_buy_order,
    cancel_sell_order,
    market_buy,
    p2p_trade,
    place_buy_order,
    place_sell_order,
    sell_into_bids,
)
from realm.economy.supply_signals import all_region_activity, trade_flows_overlay
from realm.infrastructure.movement import dispatch_shipment
from realm.infrastructure.roads import all_roads_public, build_road, set_road_toll
from realm.production.buildings import build_on_plot
from realm.production.decay import maintain_building
from realm.production.recipe_workshops import recipe_ids_on_plot_for_owner
from realm.production.schematic import validate_linear_recipe_chain
from realm.world import bootstrap_by_scenario, world_compact_dict, world_public_dict
from realm.world.tick import advance_tick

router = APIRouter()


'''

_BUCKET_DESCS = {
    "world": "world reads, tick advance, llm + code endpoints",
    "actions": "player-facing action endpoints (plots, hires, ship, accounts, business)",
    "contracts": "contract lifecycle (supply / loan / equity / service / forward)",
    "analytics": "analytics, alerts, intel, tenders, markets, bank",
    "dev": "dev-only endpoints (reset, save/load)",
}


def _emit_router_file(bucket: str, blocks: list[str], out_path: str) -> None:
    header = _ROUTER_HEADER.format(desc=_BUCKET_DESCS[bucket])
    body = "\n\n\n".join(_rewrite_for_router(b).strip() for b in blocks)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        f.write(body)
        f.write("\n")


def _emit_state_file(out_path: str) -> None:
    text = '''"""Shared dev singletons for the realm.api package.

The HTTP API's dev mode keeps a single in-memory ``World`` object that is
the source of truth for every request. ``POST /dev/reset`` reassigns this
attribute; readers in router modules access it via ``_state.WORLD`` so the
reassignment is reflected everywhere immediately.

Real production-mode persistence happens through ``realm.api.persistence``
(SQLite snapshots).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from realm.world import bootstrap_frontier

if TYPE_CHECKING:  # pragma: no cover
    from realm.world import World

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SAVE_PATH = _REPO_ROOT / "saves" / "realm_dev.sqlite"

# The current dev-mode World. Reassigned by ``POST /dev/reset``.
WORLD: "World" = bootstrap_frontier(seed=42)


def _save_path(path: str | None) -> Path:
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = _REPO_ROOT / p
    else:
        p = _DEFAULT_SAVE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
'''
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _emit_thin_app(out_path: str) -> None:
    text = '''"""FastAPI app: middleware, router registration, dev singletons.

NO game logic. NO routes defined directly here -- every route lives in a
``routes_*.py`` file under this package. The dev-mode shared world and
helpers live in ``_state``.

Tests import ``app`` from ``realm.api`` (or from ``realm.api.app``):

    from realm.api import app           # via __init__.py re-export
    from realm.api.app import app       # this module

Both paths return the same ``FastAPI`` instance.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from realm.api import (
    _state,  # noqa: F401  (kept importable for tests doing ``api._state.WORLD``)
    routes_actions,
    routes_analytics,
    routes_contracts,
    routes_dev,
    routes_world,
)

# Backwards-compat alias: legacy code (and tests) read ``realm.api.app._world``.
# We expose it as a module-attribute *getter* via ``__getattr__`` so reassignments
# of ``_state.WORLD`` (by ``POST /dev/reset``) are seen by every reader.


def __getattr__(name: str):
    if name == "_world":
        return _state.WORLD
    if name == "_save_path":
        return _state._save_path
    raise AttributeError(f"module 'realm.api.app' has no attribute {name!r}")


app = FastAPI(title="Realm Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_world.router)
app.include_router(routes_actions.router)
app.include_router(routes_contracts.router)
app.include_router(routes_analytics.router)
app.include_router(routes_dev.router)
'''
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> int:
    if not os.path.exists(APP_PATH):
        print(f"missing {APP_PATH}", file=sys.stderr)
        return 1
    with open(APP_PATH, encoding="utf-8") as f:
        src = f.read()
    _preamble, blocks = _split_into_blocks(src)
    by_bucket: dict[str, list[str]] = {b: [] for b in BUCKETS}
    for bucket, _decos, block in blocks:
        by_bucket[bucket].append(block)
    counts = {b: len(by_bucket[b]) for b in BUCKETS}
    print("Routes per bucket:", counts, "(total:", sum(counts.values()), ")")
    # Emit files.
    _emit_state_file("realm/api/_state.py")
    for bucket in BUCKETS:
        _emit_router_file(bucket, by_bucket[bucket], f"realm/api/routes_{bucket}.py")
    _emit_thin_app("realm/api/app.py")
    print("OK -- emitted _state.py, routes_*.py, and replaced app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
