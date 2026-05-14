"""Realm simulation engine (solo v1).

The package is organized into domain folders under ``realm/``. See
``engine/ARCHITECTURE.md`` for the full map. The high-level layout is:

* ``realm.core``           — IDs, ledger, inventory, RNG, time scale
* ``realm.world``          — World state, terrain, geography
* ``realm.economy``        — Markets, pricing, exchange, intelligence
* ``realm.production``     — Recipes, buildings, production tick
* ``realm.agents``         — NPC and AI agents (tier1/2/3, genesis settlers)
* ``realm.genesis``        — Genesis scenario bootstrap and scripted NPCs
* ``realm.population``     — Laborers, towns, stores, employment market
* ``realm.contracts``      — Supply / forward / loan / equity / tender
* ``realm.actions``        — Player-facing action handlers
* ``realm.infrastructure`` — Movement, logistics, energy, roads
* ``realm.events``         — Event log, world events, seasons
* ``realm.code``           — User Lua scripting layer
* ``realm.api``            — HTTP API (no game logic)

Top-level ``realm.materials`` and ``realm.tick`` exist for convenience.

For backwards compatibility, ``realm.ledger`` and ``realm.inventory`` continue
to re-export from their new ``realm.core`` locations.
"""

__version__ = "0.1.0"
