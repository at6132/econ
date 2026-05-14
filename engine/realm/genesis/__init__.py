"""Genesis scenario — bootstrapping, scripted NPCs, and named-agent arcs.

The genesis scenario is the v1 solo scenario (~50 settlers seeded into the
Frontier map). This package owns the scripted NPCs and the bootstrap helpers
that put them on the map.

Submodules:
  * ``realm.genesis.archetypes``         — Settler archetype catalog (formerly genesis_archetypes)
  * ``realm.genesis.digest``             — Daily/weekly digest builder (formerly genesis_digest)
  * ``realm.genesis.feed_hooks``         — Trigger-based world-feed emitters (formerly genesis_feed_hooks)
  * ``realm.genesis.margaux``            — Margaux NPC scripted scripts (formerly genesis_margaux_scripts)
  * ``realm.genesis.margaux_sprint5``    — Margaux Sprint 5 beats (formerly genesis_margaux_sprint5)
  * ``realm.genesis.settler_cycle``      — Settler lifecycle / migration (formerly genesis_settler_cycle)
  * ``realm.genesis.settler_names``      — Settler name pool
  * ``realm.genesis.settler_cost_basis`` — Cost-basis bookkeeping for settler agents
  * ``realm.genesis.settler_upgrades``   — Settler tier upgrade rules
  * ``realm.genesis.broker``             — Broker NPC scripts
  * ``realm.genesis.consolidator``       — Consolidator NPC (Tony) scripts
  * ``realm.genesis.energy``             — NPC energy seeding (genesis-only)
  * ``realm.genesis.road_builders``      — Road-builder NPC scripts
  * ``realm.genesis.shippers``           — Shipper NPC scripts
  * ``realm.genesis.bank``               — Bank NPC scripts (formerly genesis_bank)
  * ``realm.genesis.laborer_names``      — Name pool for labourers
"""
