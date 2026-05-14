# Realm engine — best practices

This is the short list. If you are about to write code that violates one of
these, stop and read `ARCHITECTURE.md` first.

## 1. Never mutate state outside the transaction layer

```python
# WRONG — bypasses conservation
world.ledger.balances[account] += 100_00
party_inv[material] = party_inv.get(material, 0) + 5

# RIGHT — goes through the transaction layer
world.ledger.transfer(from_account, to_account, 100_00, reason="...")
world.inventory.transfer_to(from_party, to_party, material, 5)
```

Money only moves via `ledger.transfer(...)`. Materials only move via
`inventory.transfer_to(...)` (or `inventory.move(...)` for plot-internal
movement). There is no exception to this rule.

## 2. Never use non-deterministic randomness

```python
# WRONG — different bytes every run, same seed
r = random.random()
import time; t = time.time()

# RIGHT — seeded by (world.tick, purpose)
rng = world.rng(world.tick, "ore-mining")
roll = rng.random()
```

Use `world.rng(tick, "purpose-tag")` in tick logic. Use
`make_rng(seed, *parts)` during bootstrap. The `purpose` string is part of
the seed material — change it and the stream changes, which is fine when you
*want* a new stream and a regression otherwise.

## 3. Return `ActionResult`; do not raise for rejections

```python
# WRONG
def claim_plot(world, party, plot_id):
    if world.plots[plot_id].owner is not None:
        raise ValueError("already claimed")

# RIGHT
def claim_plot(world, party, plot_id) -> ActionResult:
    plot = world.plots.get(plot_id)
    if plot is None:
        return {"ok": False, "reason": "no such plot"}
    if plot.owner is not None:
        return {"ok": False, "reason": "already claimed"}
    # ... mutate ...
    return {"ok": True, "plot_id": plot_id}
```

Exceptions are for *programmer errors* (assertion failures, bug-class). Every
expected rejection — insufficient funds, missing inventory, contract already
filled, plot already claimed — is a `{"ok": False, "reason": "..."}` result.

## 4. Type hints, everywhere

Every function on the engine side is fully type-annotated. Use:
- `PartyId`, `PlotId`, `MaterialId`, `AccountId` from `realm.core.ids` — not raw `str`
- `int` for cents (never `float` for money)
- `int` for material quantity (never `float`)
- `@dataclass(frozen=True, slots=True)` for value objects
- `TypedDict` for dict shapes that cross function boundaries

## 5. Conservation tests for anything that moves money or matter

If your change can transfer cents or materials, add (or extend) a test in
`tests/core/test_conservation*.py` or in the corresponding domain folder.
The canonical pattern:

```python
from realm.core.conservation import ConservationSnapshot

def test_my_action_conserves():
    world = bootstrap_frontier(seed=42)
    snap = ConservationSnapshot.from_world(world)
    result = my_action(world, ...)
    assert result["ok"]
    snap.assert_money_conserved(world)
    snap.assert_matter_conserved(world)
```

## 6. Imports follow the dependency graph

`core` imports nothing else from `realm`. `world` imports only `core`.
Higher layers (economy, production, …) import lower ones, never the reverse.

If you need a higher-layer symbol inside a low-layer module:
- First, ask whether the design is correct. Usually the right answer is to
  invert the dependency or hoist the helper.
- If genuinely unavoidable, **inline-import** inside the function (not at
  module top). This is how the production/decay/events cycle was broken.

Top-level `from realm.X import ...` should never form a cycle.

## 7. Keep `actions/*.py` files small and single-purpose

One file per action group (plot, business, employment, production, shipping,
…). Helpers live next to the action that needs them. If a file grows past
~400 lines, split it.

## 8. The API is a transport layer, not a logic layer

`realm/api/routes_*.py` files are short. They:
1. Parse the request,
2. Call an action handler (`realm.actions.*`) or a serializer
   (`realm.world.serialization.*`),
3. Wrap the response in JSON.

Logic that isn't trivial validation goes in `actions/`. If you find yourself
writing more than a dozen lines of "logic" inside a route, you are in the
wrong file.

## 9. Naming

- Describe **what** a thing is, not **how** it is implemented.
- `claim_plot`, not `set_plot_owner_to_party`.
- `world_public_dict`, not `serialize_world_to_dict_v2`.
- Files: lower_snake_case. Classes: `UpperCamel`. Functions / vars: `snake_case`.
- `_leading_underscore` for module-private helpers.

## 10. Comments

- Comments explain **why**, not **what**.
- Code that "narrates itself" (`# loop over plots`) is noise — delete it.
- A comment is appropriate when:
  - There is a non-obvious trade-off ("we batch every 10 ticks because…").
  - There is a constraint the code can't express ("must be ≥ this because the API caps at…").
  - There is a deferred decision ("this stays here until tier-3 lands, see issue #N").

## 11. Determinism extends to test fixtures

`tests/turnkey_fixtures.py` builds worlds with fixed seeds. Don't reach into
the OS clock or environment from inside the engine. Tests that need an
"agent talked to LLM" effect should mock the call, not skip determinism.

## 12. When in doubt, read `ARCHITECTURE.md`

The architecture doc lists which folder owns which concern. If your change
spans three folders, you probably have the dependency direction wrong, or
you have invented a new domain and should propose it before implementing.
