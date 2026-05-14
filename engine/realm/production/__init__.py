"""Production — recipes, buildings, the production tick.

Submodules:
  * ``realm.production.production``       — start_production, tick_production,
                                             auto-list/auto-restart logic
  * ``realm.production.recipes``          — Catalog of all recipes
  * ``realm.production.recipe_sites``     — Terrain gates per recipe
  * ``realm.production.recipe_workshops`` — Workshop-to-recipe mappings
  * ``realm.production.buildings``        — Catalog and ``build_on_plot``
  * ``realm.production.schematic``        — Linear chain validation
  * ``realm.production.spoilage``         — Material spoilage tick
  * ``realm.production.storage_caps``     — Per-building storage caps
  * ``realm.production.decay``            — Building decay/maintenance tick

Backwards-compat: ``from realm.production import start_production`` etc.
keeps working through the lazy ``__getattr__`` below. We CANNOT eagerly
re-export from ``realm.production.production`` here because that module
transitively imports ``realm.events.event_log``, which imports
``realm.world``, which imports ``realm.production.recipes`` -- a cycle
that only resolves if ``realm.production.__init__`` does not eagerly
load any submodule during package initialization.

Anything defined at module scope in ``realm.production.production`` is
accessible via ``realm.production.NAME`` (functions, dataclasses, and
constants like ``CONTINUOUS_RUN_COUNT`` and ``AUTO_LIST_MARGIN_BPS``).
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    # Lazy delegate to the production.production submodule (avoids the
    # event_log -> world -> production.recipes circular import that would
    # fire if we eagerly re-exported here).
    #
    # Sub-modules of this package (production, recipes, buildings, ...) must
    # be loaded by importlib's normal submodule machinery, NOT via this
    # delegating __getattr__ -- otherwise the load goes infinitely
    # recursive on ``from realm.production import production``.
    if name in (
        "production",
        "recipes",
        "recipe_sites",
        "recipe_workshops",
        "buildings",
        "schematic",
        "spoilage",
        "storage_caps",
        "decay",
    ):
        import importlib

        return importlib.import_module(f"realm.production.{name}")
    import importlib

    _production = importlib.import_module("realm.production.production")
    if hasattr(_production, name):
        return getattr(_production, name)
    raise AttributeError(f"module 'realm.production' has no attribute {name!r}")
