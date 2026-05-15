"""Run one Tier-3 LLM planning step from the command line.

Usage (from ``engine/`` with dev deps)::

    pip install -e ".[llm]"
    set ANTHROPIC_API_KEY=...
    python -m realm.llm_cli --party llm_margaux

Optional ``--load`` / ``--save`` use the same SQLite snapshot format as ``/persistence/*``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Realm Tier-3 Haiku planning step")
    p.add_argument("--scenario", default="genesis", help="bootstrap scenario if not loading (incl. frontier)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--party", default="llm_margaux")
    p.add_argument("--load", type=Path, default=None, help="SQLite snapshot to load first")
    p.add_argument("--save", type=Path, default=None, help="SQLite path to write after step")
    p.add_argument(
        "--code-status",
        action="store_true",
        help="print JSON from code_layer_public_status (Lua optional extra) and exit",
    )
    args = p.parse_args()

    if args.code_status:
        from realm.code.user_code import code_layer_public_status

        print(json.dumps(code_layer_public_status(), indent=2))
        return 0

    from realm.agents.tier3 import plan_llm_party_once
    from realm.core.ids import PartyId
    from realm.api.persistence import load_snapshot, save_snapshot
    from realm.world import bootstrap_by_scenario

    if args.load is not None:
        world = load_snapshot(str(args.load))
    else:
        world = bootstrap_by_scenario(seed=args.seed, scenario=args.scenario)

    result = plan_llm_party_once(world, PartyId(args.party))
    print(json.dumps(result, indent=2, default=str))

    if args.save is not None:
        save_snapshot(str(args.save), world)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
