# 19 — Phase 9 Realism Audit (Scoping)

> **Purpose:** before we touch the UI, walk the entire engine against the 7 design pillars (doc 02), the 9 primitives (doc 03), and the 10 laws (doc 04) and write down every place where the simulation lets you do something the design says you shouldn't be able to do. Avi flagged "you can dock and unload your boat anywhere — should require a port"; this doc finds the rest.
>
> **Status:** Phase 9 implemented and closed in slices 9A-9I. The original audit remains below for traceability; the closure summary is in section C.
>
> **Severity scale:**
> - **P0** — breaks a pillar or a law (e.g. free money, geography ignored, conservation hole). Must fix.
> - **P1** — design spec promises this; engine doesn't have it (e.g. plot trading). Must fix unless explicitly deferred.
> - **P2** — flavor / realism polish (e.g. mass-weighted shipping). Nice to have for Phase 9.
> - **P3** — known-deferred (e.g. player-issued currencies, full identity costs). Document, don't fix.

---

## A. Headless probe — what the engine actually does

Bootstrap: 950 laborers, 28 parties, 4 towns, 1,728 plots (48×36, seed 42).
30 game-days of `advance_tick`. Conservation holds (`ledger_delta = 0`,
`matter_delta ≥ 0` from extraction).

**Behavioral signal (most interesting bits of `_phase9_summary.json`):**

| signal | observed | implied gap |
| --- | --- | --- |
| `market_list` events | 2,021 | agents churn buy/sell orders constantly |
| `market_cancel` events | 1,964 | ~67 list/cancel cycles per game-day — price discovery is broken |
| `production_start` | 6 | **the economy is idle** — almost no production runs |
| `production_done` | 4 | only 4 recipes complete in a month with 950 laborers available |
| `job_posted` / `job_filled` | 18 / 18 | only 18 of 950 laborers ever get hired |
| `ship_dispatch` / `ship_deliver` | 0 / 0 (sampled) | the inter-island demand model from 7F never fires within 30 days |
| `survey` | 0 | nobody surveys speculatively |
| `bank_loan_open` | 0 | financial system inert |
| `world_feed` lines | 13 | laborer deaths and consumer purchases very rare |

The 30-day window is short, but **the order of magnitude is wrong**: a real
economy at this scale should show hundreds of trades, dozens of jobs, and
visible inter-island shipments within a week. The detailed code findings
below explain why.

---

## B. Findings by primitive / law

### B1. MOVEMENT (Pillar 3, Law 3, Primitive 4)

#### B1.1 — Docking requires no port `[P0]` *(Avi's example)*
- **Spec:** Primitive 1 has `coastal_access` and `harbor_depth` as intrinsic plot properties. Primitive 4 expects vessels and ports. Pillar 3 says geography matters.
- **Engine:** `realm/infrastructure/movement.py::dispatch_shipment` accepts any owned plot at both ends. The `dock` building exists but only grants a **speed bonus** (`HARBOR_TRANSIT_SPEEDUP_BPS`); there is **no gate**. A laborer plot on island 0 can ship to a mountain plot on island 3 with no harbor at either end.
- **Fix:** Inter-island shipments must originate at a `dock` plot on the origin island and deliver to a `dock` plot on the destination island. Lift the speed-bonus check into a hard gate when `is_inter_island_shipment(...)` is true. Add `reason: "origin requires a dock to ship across water"`.
- **Effort:** 1–2 hours engine + 6–8 tests (build dock first, then ship; bare plot blocked; intra-island unchanged).

#### B1.2 — No vessels / no truck entities `[P1]`
- **Spec:** Primitive 4 says "build/own transport assets (vessels, vehicles)". Composing example: "shipping company ⇒ 1+ coastal plots + vessels".
- **Engine:** No vessel/vehicle data model. Shipping is abstract: pay a fee, time elapses, goods appear. Anyone can "be a shipping company" with zero capital infrastructure.
- **Fix (minimum viable):** introduce a `Vessel` material/asset (or `VehicleAsset`) gated by `dock` + a `boat` recipe. `dispatch_shipment` for inter-island deducts vessel-hours and consumes a small amount of fuel/feed-corn-equivalent per voyage. Defer fleet capacity to Phase 10.
- **Effort:** medium (4–6 hours engine + tests). Could be deferred to Phase 10 if Phase 9 is tight.

#### B1.3 — Shipping cost is unit-count, not mass `[P2]`
- **Spec:** Materials have `mass_per_unit_kg`. Realistic transport scales with weight.
- **Engine:** `BASE_SHIP_FEE_CENTS + dist * PER_TILE_SHIP_CENTS * ocean_mult` ignores mass entirely. Hauling 1 unit of iron_ingot (7,850 kg) and 1 unit of grain (780 kg) cost the same.
- **Fix:** multiply per-tile rate by `material.mass_per_unit_kg / REFERENCE_MASS_KG` (cap at 5×). Falls naturally out of the existing mass schema.
- **Effort:** 30 min engine + a few tests.

#### B1.4 — Receiving fee goes to `system:reserve`, not the dock owner `[P1]`
- **Spec:** Pillar 1 — players invent the content. A port that handles cargo should earn revenue.
- **Engine:** `receiving_fee_cents` flows to `system_reserve_account` (`movement.py:330`). Money exits the player economy.
- **Fix:** credit the destination plot's owner; if no owner, fall back to system reserve. Pairs naturally with the B1.1 dock-required fix.
- **Effort:** 30 min + tests.

#### B1.5 — No fuel cost on shipping `[P1]`
- **Spec:** Law 4 — energy required. Movement of goods is one of the canonical energy sinks.
- **Engine:** transit consumes time and money but not fuel/electricity. A shipper with no power plant can run a global logistics business indefinitely.
- **Fix:** `dispatch_shipment` deducts e.g. 1 unit of `coal` or `electricity` per N tiles from the shipper's inventory (route-operator path: from the operator's inventory). Pair with B1.2 if vessels exist.
- **Effort:** 1 hour + tests.

#### B1.6 — Road tolls are paid even without crossing the road `[P2]`
- **Spec:** Toll = use-based.
- **Engine:** `roads.compute_road_savings_and_tolls` returns tolls for the deterministic A→B path *whether or not the path actually uses the road*. Verify on the path-overlap branch; if not, fix.
- **Effort:** 30 min audit + small fix.

---

### B2. LAND (Primitive 1, Pillar 3)

#### B2.1 — No plot transfer/sale between players `[P1]`
- **Spec:** Primitive 1 lists `Sell/transfer a plot to another player` and `Lease a plot to another player` as core capabilities. Worked example "research/surveying firm" depends on leasing.
- **Engine:** `realm/actions/plot_actions.py` has `claim_plot`, `survey_plot`, and survey-report markets — **no plot transfer action exists**. `grep -r 'def transfer_plot\|def sell_plot\|def lease_plot'` returns no matches. The bank can seize collateral plots (`bank.py`) but that's the only way ownership ever changes hands after a claim.
- **Fix:** add `transfer_plot(world, from, to, plot_id, price_cents)` (atomic cash + ownership swap), `list_plot_for_sale`, and `buy_plot_listing`. Lease can wait; spot-sale is the must.
- **Effort:** 2–3 hours engine + 8–10 tests.

#### B2.2 — Surveying is instantaneous `[P2]`
- **Spec:** Law 2 — time has scale.
- **Engine:** `survey_plot` pays $500 and flips `plot.surveyed = True` in one tick. Real surveys take days.
- **Fix:** add `SurveyJob` with duration_ticks (e.g. 1 game-day), block production on the plot until complete. Already partially modeled by `deep_survey` machinery; mirror that.
- **Effort:** 1–2 hours + tests.

#### B2.3 — Survey requires ownership; "speculative surveyor" business impossible `[P1]`
- **Spec:** Primitive 1 — "research/surveying firm: visits, surveys, leaves" composes from primitives.
- **Engine:** `survey_plot` rejects unless `plot.owner == party`. A surveyor cannot run a business surveying others' plots on contract.
- **Fix:** allow `survey_plot` if (a) plot owner is `None` (paid speculative survey on unclaimed land — the report still belongs to the surveyor), or (b) a surveyed-by-contract clause: the surveyor is a `permitted_surveyor` on the plot, with the owner having signed off. Simpler: add `survey_plot_for(world, surveyor, plot_id, price_cents)` that requires plot.owner to pre-authorize via a contract row.
- **Effort:** 2 hours + tests.

#### B2.4 — No claim limit, no contiguity bonus `[P2]`
- **Spec:** Primitive 1 — "claim subject to availability rules per game mode".
- **Engine:** `claim_plot` has a per-plot density-based price (`claim_cost_cents_for_plot`) but no cap, no scaling penalty for owning N unrelated plots, no contiguity bonus. A solo player or bot can sweep entire islands one tile at a time at little cost.
- **Fix:** progressive claim fee: `cost * (1 + 0.2 * plots_owned)`. Don't need a hard cap.
- **Effort:** 30 min + tests.

---

### B3. PRODUCTION (Primitive 6, Law 4)

#### B3.1 — Fishing/tidal recipes ignore water adjacency in many code paths `[P0]`
- **Spec:** coastal-only recipes (`fishing`, `tidal_power`).
- **Engine:** `recipe_allowed_on_plot` *does* call `plot_is_coastal` — looks correct. **Verify** by trying to start fishing on an inland plot in a test. **(Looks OK on read; flagging for confirmation.)**

#### B3.2 — Tools never wear out `[P1]`
- **Spec:** Law 5 — things decay without maintenance. Equipment "moderate decay, accelerated by use".
- **Engine:** `hand_chop`, `hand_mine_*`, `fishing` recipes require a tool (e.g. `pick_axe`) but the tool is never consumed or damaged. Buy one pickaxe, mine forever.
- **Fix:** each tool-using recipe has a probability (e.g. 2 %) of consuming the tool on completion; or a `tool_uses_remaining` integer on a per-stack basis. Probabilistic consumption is simplest and consistent with the RNG model.
- **Effort:** 1 hour + tests.

#### B3.3 — Recipe `labor_cents` sinks to `system:reserve` `[P1]`
- **Spec:** Wage payments should flow to laborers (Primitive 3).
- **Engine:** `recipes.py` comment: "paid to system reserve at production start (wage reserve)". A production run sinks money out of the player economy; it does not pay a real worker.
- **Fix:** **only** charge labor_cents if the plot has a hired laborer through the employment market; redirect to that laborer's cash account. If unstaffed, fail to start production with `reason: "no worker"`. Pair with the already-existing Phase 7 employment market.
- **Effort:** 1–2 hours + tests. **High-value:** ties production directly to the live labor pool, fixes the "idle laborer + no production" gap from the headless run (A).

#### B3.4 — Production has no per-tick capacity / no congestion `[P2]`
- **Spec:** Primitive 6 — throughput is a property.
- **Engine:** A single foundry plot can run unlimited concurrent production jobs; nothing in `production.py` caps active jobs per plot. Multi-shift logistics impossible to model.
- **Fix:** `max_concurrent_jobs = 1` per `building_id` (or per recipe), parameterised. Already half-modeled via `world.production_jobs` but not enforced.
- **Effort:** 1 hour + tests.

#### B3.5 — Some recipes "manufacture" mass `[P2]`
- **Spec:** Mass balance — outputs ≤ inputs accounting for waste.
- **Engine:** `mine_iron_ore` outputs 2 iron_ore (5,000 kg/unit × 2 = 10,000 kg) from only `electricity` (0 kg/unit) + labor. The "mass" comes from the plot's subsurface — designer-given matter. Acknowledged exception per `inventory.add` docstring, but extraction recipes should at least deplete `subsurface.<grade>` over time so a plot eventually exhausts.
- **Fix:** decrement the relevant subsurface grade by a tiny amount per extraction (e.g. 0.001 per unit). When grade < 0.3 (the gate), recipe stops working. Already half-spec'd in doc 03 ("subsurface composition" — exhaustion isn't called out explicitly but mining sites do run dry historically).
- **Effort:** 1–2 hours + tests. Could defer.

#### B3.6 — Some recipes produce slag, others don't `[P3]`
- **Engine:** `smelt_iron` produces no slag, `steel_alloy` produces 2 slag, `lime_burn` produces 3. Inconsistent — IRL all smelting yields slag.
- **Fix:** unify so any high-temperature smelt yields ≥ 1 slag per unit ore. Low priority.
- **Effort:** 1 hour + tests; pure recipe-table tweaking.

---

### B4. LABOR (Primitive 3)

#### B4.1 — Most laborers have no `home_town` and never participate in consumer economy `[P0]`
- **Spec:** Pillar 1 — players invent content. Pillar 4 — emergent demand. Phase 7 explicitly built consumer demand on top of laborers.
- **Engine:** `population/towns.py:_assign_residences_at_bootstrap` pins one laborer to each residence slot; **everyone else is left "floating"**. From the headless run: ~24 of 238 laborers per town have a home_town, so ~92 % of the workforce never buys at stores. Nothing in the simulation builds new residences in response to that shortage — `genesis/archetypes.py` has no `residential_developer` pattern.
- **Fix:** (a) **emergent residences** — add a developer archetype that detects unhoused laborers in a town and builds a residence when ROI clears; (b) interim: increase initial residence slots per residential plot from "1" to e.g. `town_pop / num_residences + 2`. (a) is the right fix; (b) keeps the simulation moving while (a) gets built.
- **Effort:** (b) 30 min; (a) 3–5 hours + behavior tests. **The single highest-leverage realism fix in the audit.**

#### B4.2 — Laborer cash sinks to `system:reserve` on death and retirement `[P1]`
- **Spec:** Law 1 — money conserved through designed channels. Money exiting laborer accounts back to reserve is technically a designed channel, but it's deflationary at population scale.
- **Engine:** `population/laborers.py::_kill_laborer` and `_retire_laborer` both sweep remaining cash to system_reserve. With ~1 % daily mortality at population scale, this leaks 10s of thousands of cents per game-day back into the reserve.
- **Fix:** sweep to a **town's** treasury account (small) and/or to a **named heir** if one exists; default to system_reserve only when the laborer is unhoused. A town fund could finance residences (closes the loop with B4.1).
- **Effort:** 1 hour + tests.

#### B4.3 — Laborers retire at hardcoded age `[P1]` *(prior agent observed this in Phase 8)*
- **Engine:** every laborer dies/retires at ~100 game-days. The Phase 8F integration test had to stagger initial ages to spread out retirements. Birth rate is a stub.
- **Fix:** real birth function (children of housed laborers; needs a `partner_id` and a per-tick birth-roll). At minimum, **stagger initial ages at bootstrap** (uniform 0..70 days).
- **Effort:** 30 min for staggering; 3 hours for real births.

#### B4.4 — No child labor / age-of-work gate `[P3]`
- **Spec:** primitive 3 doesn't talk about minors. The simulation has one adult-laborer class.
- **Fix:** none for v1. Note for future.

---

### B5. MONEY (Primitive 5, Law 1)

#### B5.1 — Bank loans never auto-deduct `[P0]`
- **Spec:** Primitive 8 worked example: "Penalty for default: forfeit collateral plot."
- **Engine:** `genesis/bank.py::tick_bank_loans` increments `missed_payments` and applies reputation damage, but **never tries to actually take payment** from the borrower's cash account, even when funds exist. After 2 misses, collateral is seized. A borrower with $100,000 in cash can let a $1,000 loan default by simply not initiating payments. **This is a free-money channel** (you keep your principal and lose only a plot you may not care about).
- **Fix:** in `tick_bank_loans`, when `world.tick >= next_due_tick`, *first* attempt `ledger.transfer(debit=borrower_cash, credit=lender_cash, amount_cents=installment)`. Only mark missed if the transfer fails (insufficient funds). Reputation damage and collateral seizure apply only on real default.
- **Effort:** 1 hour + tests. **High-value P0.**

#### B5.2 — Most loan products `requires_collateral: False` `[P1]`
- **Engine:** `bank.py:55-71` — the three default loan products have `requires_collateral: False`. Without collateral, defaulting on a loan has only a reputation cost; you keep the principal. Free-money channel.
- **Fix:** require collateral on ≥ 1 product; for "signature loans", drop principal-default-amount × 1.5 from `system:reserve_treasury` to recoup. Cleanest: require a collateral plot.
- **Effort:** 30 min + tests.

#### B5.3 — Survey, claim, and recipe-labor fees all sink to `system:reserve` `[P1]`
- Already covered: claim fee, survey fee, recipe wage, receiving fee. The reserve grows mechanically over time. Money keeps circulating only because of the new-settler grant + boom NPCs + Margaux-scripted injections.
- **Fix:** redirect labor_cents to laborers (B3.3), receiving fee to dock owner (B1.4); leave claim and survey fees as designed sinks (they're explicitly "land registry" and "survey office" fees in the design intent — fine for v1 but document in `13_PHASED_TODO.md`).

---

### B6. MARKETS (Primitive 7)

#### B6.1 — Order-book churn dominates everything (the "67 list/cancel per day" finding) `[P1]`
- **Headless evidence:** 2,021 list events + 1,964 cancel events = an effective net of ~57 fills per day across 950 agents, 28 active parties. Tier 1/2 agents are jittering orders aggressively.
- **Engine:** `agents/tier1.py`, `tier2.py`, `tier3.py` re-quote on every tick they run.
- **Fix:** add a per-party `min_requote_interval_ticks` (e.g. one game-hour) and a `book_dampener` so an order is only re-listed if `delta_price_bps > 200` from prior. This is a pure agent-side fix; the engine is fine.
- **Effort:** 1 hour + agent tests.

#### B6.2 — No bid-ask spread tracking; no market-maker rebate `[P2]`
- **Spec:** Primitive 7 — "build market-making businesses". No spread incentive in the engine, so no market-maker emerges.
- **Fix:** pay 0.5 % of fill price to whichever side rested (passive order), charge 0.5 % from the aggressor. Net-zero designed-rebate flow (already a small Phase 4 candidate). **Defer to Phase 10 if Phase 9 is tight.**

---

### B7. CONTRACTS (Primitive 8)

#### B7.1 — Force majeure only handles storms `[P1]`
- **Spec:** Contracts include penalties + grace conditions. Phase 8 introduced disasters (drought, blight, mine collapse, seismic, epidemic) but only storm grants supply-contract extensions.
- **Engine:** `contracts/social.py::tick_supply_contract_breaches` only checks `active_storms`.
- **Fix:** generalise `force_majeure_window_ticks(world, contract)` to inspect all active disasters that touch the contract's island(s) and take the max. Drought → +2 game-days for grain contracts; mine collapse → +5 days for ore contracts; etc.
- **Effort:** 1 hour + tests.

#### B7.2 — No lien on remaining assets after partial liquidated-damages payment `[P1]`
- **Engine:** `tick_supply_contract_breaches` pays liquidated damages capped at `world.ledger.balance(sc)` (supplier's cash). If supplier is broke, buyer gets $0 even when supplier owns valuable inventory or plots.
- **Fix:** after cash exhausts, place a lien against supplier (no new claims, no new loans) until damages settled, OR seize materials from supplier's inventory at last-trade prices up to remaining damages. Lien is simpler.
- **Effort:** 1–2 hours + tests.

#### B7.3 — No employment contract breach mechanics `[P2]`
- **Spec:** worked example: employment contract — "either side may terminate with 7 days' notice".
- **Engine:** `realm/population/employment.py` has hire/fire actions but no notice period; no severance.
- **Fix:** add `notice_period_ticks` to employment contracts; firing during notice owes the laborer `notice_ticks/TICKS_PER_GAME_DAY * wage_per_day_cents`.
- **Effort:** 1 hour + tests.

---

### B8. INFORMATION (Law 6)

#### B8.1 — Public order book is fully visible with no lag `[P2]`
- **Spec:** Law 6 — "public order books (with delay if information cost is enabled)".
- **Engine:** order book is read directly by all agents. No delay layer.
- **Fix:** introduce `world.market_book_snapshot_tick` updated every 60 ticks (1 hour); all reads use the snapshot. Premium analytics already exists; tier the freshness.
- **Effort:** 1 hour. Could defer.

#### B8.2 — Subsurface gate works (good) but is binary `[P3]`
- Already enforced. Note for future: granular reveal (e.g. survey reveals iron + coal but not platinum without deep survey) is already modeled. Fine.

---

### B9. REPUTATION + IDENTITY (Law 7, Law 8)

#### B9.1 — Reputation is purely counters (`honored` / `breached`) `[P2]`
- **Spec:** Law 7 — also tracks payment punctuality, delivery punctuality, dispute history.
- **Engine:** just two integers per party.
- **Fix:** add `avg_payment_lateness_ticks`, `avg_delivery_lateness_ticks`, `last_breach_tick`. Light schema add; bank uses them to gate loan rates.
- **Effort:** 2 hours + tests.

#### B9.2 — No identity cost (solo only) `[P3]` *(known deferred)*
- Doc 04 acknowledges public-mode identity cost is multi-player. Solo doesn't need it. Document, don't fix.

---

### B10. DECAY (Law 5)

#### B10.1 — Tools don't decay `[P1]` — see B3.2

#### B10.2 — Roads don't decay `[P1]`
- **Engine:** `infrastructure/roads.py` — built roads are permanent. Real roads need resurfacing.
- **Fix:** road condition decays at e.g. 0.1 % per game-day; tolls drop linearly with condition; owners can pay a maintenance fee (similar to building maintenance) to restore. Already half-modeled for buildings; mirror.
- **Effort:** 1–2 hours + tests.

#### B10.3 — Buildings decay (already implemented, good) `[OK]`
- `production/decay.py` works; maintenance schedules in `buildings.py` are wired up.

---

### B11. WORLDGEN + ENVIRONMENT

#### B11.1 — No water material; laborers don't drink `[P2]`
- **Spec:** Primitive 2 — physical materials with realistic properties. Real economies have water demand.
- **Engine:** there is no `water` material; laborers have `food`, `fuel`, `shelter` needs only.
- **Fix:** add `water` material; require it as a daily need (cheap, free near rivers/coasts, costly inland — geography matters). Phase 2 of this fix: irrigation costs water, raising costs in dry regions.
- **Effort:** 2–3 hours + tests. **Could be deferred to Phase 10** as a "second-tier realism" pass.

#### B11.2 — Climate / temperature / seasons partially modeled `[P3]`
- Phase 8A added a seasonal calendar with recipe blockers (grow_grain in winter). Temperature per plot is not used (Primitive 1 lists it). Acceptable for v1.

---

## C. Phase 9 — closure summary

Phase 9 is closed. Implemented slices:

- **9A - Geography gates + vessels-as-assets:** inter-island shipments require origin/destination docks, shipper-owned vessel, and fuel; destination dock owner receives handling fees; shipyards can build vessels.
- **9B - Plot trading + speculative surveying:** plot transfer/list/cancel/buy flow plus authorized survey access.
- **9C - Real labor wages:** production labor payments route to real laborers when possible, with deterministic local selection and reserve fallback.
- **9D - Bank loan correctness:** due payments auto-deduct when cash exists; trusted tier requires collateral.
- **9E - Force majeure + liens:** supply contracts get generalized disaster grace; unpaid damages create liens that drain future cash flow.
- **9F - Wear and decay:** tool wear, road condition decay, and road maintenance.
- **9G - Housing developer + treasury sweep:** bootstrap has more basic homes, home-builder NPCs expand residences, homeless laborers fill new slots, and dead/retired laborer cash flows to town treasuries.
- **9H - Order-book sanity:** Tier 2 cancel/repost behavior is gated by a quote cooldown and material price movement, with a microfee on cancels.
- **9I - Realism polish:** mass-weighted shipping, progressive claim fees, and staggered starting laborer ages.

Deferred out of Phase 9 by design: water material/daily thirst, public order-book information delay, market-maker rebates, full employment notice mechanics, richer reputation statistics, and birth/child modeling. These are Phase 10+ candidates because Phase 9's closure target was final realism correction without introducing new primitives.

Final headless probe (`python _phase9_headless.py`, seed 42, 30 game-days):

- Ledger conservation held: `ledger_delta = 0`.
- Population stayed alive: `final_laborers = 950`.
- Housing target cleared at bootstrap after final tuning: `602 / 950 = 63.4%` housed.
- Production is live: `production_done = 589`, `production_start = 264`, `laborer_wage_paid = 318`.
- Order-book churn is controlled: `market_list = 66` over 30 game-days, down from the original audit's 2,021 in the same window.
- Inter-island economy is visible: `inter_island_buy = 4`, route operators registered/repriced, and the new dock/vessel/fuel gates are covered by tests.

## C0. Original Phase 9 plan

Sort the above by severity, group into shippable slices:

### Slice 9A — Geography gates (Avi's example) `[~4 hours]`
- B1.1 dock-required for inter-island ship
- B1.4 receiving fee credits dock owner
- B1.5 fuel cost per voyage (basic version: 1 unit coal per 20 tiles)
- Tests + integration test

### Slice 9B — Plot trading `[~3 hours]`
- B2.1 transfer / list / buy plot
- B2.3 speculative surveying (paid survey on others' plots via contract)
- Tests

### Slice 9C — Production attached to real labor `[~3 hours]`
- B3.3 recipe wages go to a hired laborer instead of `system:reserve`; fail-to-start if unstaffed
- Closes a P0 conservation/realism loop and immediately unblocks the "950 laborers idle" finding from the headless run.

### Slice 9D — Bank loan correctness `[~2 hours]`
- B5.1 auto-deduct on due-tick
- B5.2 collateral required on at least one product
- Tests

### Slice 9E — Force majeure + lien `[~3 hours]`
- B7.1 generalise force-majeure
- B7.2 lien against breached supplier
- Tests

### Slice 9F — Wear-and-decay completeness `[~3 hours]`
- B3.2 tool wear (probabilistic consumption)
- B10.2 road decay + maintenance
- Tests

### Slice 9G — Emergent housing developer `[~5 hours]`
- B4.1 archetype that builds residences when ROI clears, partly funded by town treasury seeded by B4.2 laborer-death sweep
- B4.2 redirect dead-laborer cash to a town treasury (account model + seeding)
- Tests + 60-day headless re-run gate (target: ≥ 60 % of laborers housed within 30 days)

### Slice 9H — Order-book sanity `[~1 hour]`
- B6.1 agent re-quote dampener (1-hour cooldown, 2 % price-delta threshold)
- Headless re-run: target `< 20` market_list events per agent per day

### Slice 9I — Realism polish (optional in Phase 9) `[~3 hours]`
- B1.3 mass-weighted shipping cost
- B2.2 surveying takes a game-day
- B2.4 progressive claim fee
- B7.3 employment notice period
- B9.1 richer reputation counters

**Recommended Phase 9 scope:** **9A, 9B, 9C, 9D, 9E, 9F, 9G, 9H.** ~24 hours of work; covers every P0 and every P1 except identity (deferred) and intel delay (deferred). Slice 9I is the "if we have time" pile.

**Gate to close Phase 9:** a fresh 60-game-day headless run shows:
1. Conservation holds (already does)
2. Inter-island shipments only originate at `dock` plots — observable via event filter
3. At least 60 % of laborers housed by day 30
4. At least 100 `production_done` events over 60 days
5. At least 1 `bank_loan_auto_paid` event observed
6. `market_list` rate ≤ 20 per agent per day
7. All existing tests still pass

---

## D. Phase 10 — proposal

After Phase 9 closes the realism gaps, **Phase 10 = "final feature push + headless playtest gate"**, in three slices.

### Slice 10A — The missing primitives in the worked examples
The five worked-example businesses in doc 03 (shipping co., SaaS, bank, speculator, surveying firm) should each be reproducible end-to-end in solo by a single LLM-driven settler. Right now:
- Shipping company — needs vessels (B1.2)
- Bank — exists, but loan flow needs B5.1 first
- SaaS — Phase 4+; out of scope
- Speculator — already works
- Surveying firm — needs B2.3 first

So Phase 10A is `vessels as assets` + `commodity speculator archetype` + `traveling surveyor archetype`. ~6–8 hours.

### Slice 10B — Companion analytics + day-1 player onboarding
Right now a new player sees a dense data UI with no narrative. We should add:
- a "first 7 days" guided arc in solo: Margaux-style prompts that walk the player through claim → survey → produce → sell first time
- a tutorial sub-scenario (uses the same engine; sets `scenario_id="tutorial"`)
- analytics endpoint coverage check (no UI work — just make sure every primitive has at least one analytics endpoint)

### Slice 10C — Final 365-game-day headless playtest gate
- A `tests/integration/test_phase10_year_long.py` that runs a full game-year and asserts:
  - 1+ active business of each composing-example type (shipping, bank, speculator, surveyor)
  - At least 10 successful supply contracts honored
  - At least 1 bankruptcy + 1 recovery
  - At least 1 boom-event price spike triggers behavior changes
  - Conservation holds end-to-end
  - Margaux delivers at least 8 messages across the year
- This is the gate before Avi starts UI in Phase 11.

**Phase 10 effort total: ~18–22 hours.** Sets up Phase 11 (UI) with a fully-functioning headless engine that's known to play coherently for a game-year.

---

## E. Out of scope / explicitly deferred

- Player-issued currencies (doc 03 — v2+)
- Lua sandbox / code primitive (doc 03 — v2; Phase 4+)
- Mobile companion (post-launch)
- Multiplayer features (Phase 11+)
- Identity-cost / account farming protection (multiplayer only)
- Full 3D / fancy graphics (locked aesthetic)

---

## F. Notes for the Phase-9 agent

- Every change must keep all 130 existing tests green.
- Every slice adds tests at the engine level (no API/UI work).
- Headless probe script (`engine/_phase9_headless.py`) stays in the repo for future regression — it's a 6-minute "is the economy alive?" gate.
- All P0 fixes are economy-correctness fixes; they go first. P1s are spec-completeness; P2s are polish.
- If a fix would change a primitive or a law, stop and surface it; otherwise implement and commit.
