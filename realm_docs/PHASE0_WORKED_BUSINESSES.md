# Phase 0 — Worked Player Businesses (test-gate artifact)

> **Phase 0 test gate (`13_PHASED_TODO.md`):** "Can you describe, in one paragraph each, exactly what 5 different player-invented businesses look like — including which primitives they use, what their daily activities are, and how they make money?"

Doc 03 already lists five canonical examples (shipping, SaaS, bank, speculator, surveying firm). This file does the test gate properly: **five different businesses than those**, each composed only from the 9 primitives in [`03_PRIMITIVES_SPEC.md`](03_PRIMITIVES_SPEC.md), with no new mechanics invented. If any of these would require a tenth primitive, that's a signal to revise doc 03 before continuing.

The 9 primitives (shorthand): **(1) Plots · (2) Materials · (3) Labor · (4) Time/Distance/Movement · (5) Capital · (6) Production · (7) Markets · (8) Contracts · (9) Code**.

---

## Business 1 — Driftwood Timber & Lumber (vertically integrated producer)

**Primitives used:** Plots, Materials, Labor, Movement, Capital, Production, Markets, Contracts.

**Setup.** A coastal forested **plot** plus an inland **plot** with a sawmill. The owner extracts surface timber from the forest plot via a logging operation, moves the raw timber by wagon to the sawmill plot, and processes it into graded lumber.

**Daily activity.** Log the morning shift on the forest plot (consumes **labor** wages, produces raw timber **material** subject to a daily throughput cap from the **production** recipe). Dispatch the day's output toward the sawmill — the wagons sit in transit for one game-day per Law 3 (**movement** has cost). At the sawmill, lumber recipes consume timber + labor + a small energy input and emit graded lumber. The owner keeps a stockpile and posts daily sell **orders** on the lumber **order book** at slightly under regional ask. Two long-term **supply contracts** — one with a coastal shipbuilder, one with a builder in the next region — guarantee a base volume each week regardless of spot prices.

**Revenue.** Spot sales of lumber on the order book + delivery payments under the two supply contracts. Margin is the spread between (timber wages + sawmill labor + energy + decay maintenance) and the sale price of finished lumber. The vertical integration means they capture two margins (extraction + processing) instead of one.

**Why it works.** Pure composition of plot + materials + labor + production + movement + market + contracts. No new primitive needed. Conservation holds — timber comes from the surveyed forest plot, lumber is the production output of timber + energy.

---

## Business 2 — Hearthlight Power Co. (regional energy utility)

**Primitives used:** Plots, Materials, Labor, Capital, Production, Markets, Contracts.

**Setup.** A single inland **plot** hosts a fuel-burning power plant. The plot was chosen because the surveyed subsurface contains a coal seam — extraction + combustion happen on-site. The utility's customers are every other producer in the region, because Law 4's sub-law makes energy a *regional* good: their plant is the only source of energy in the region until someone else builds one.

**Daily activity.** Mine coal on-plot (**production** recipe consuming labor → coal **material**). Burn coal in the plant (another production recipe consuming coal → energy). Maintain the plant against decay (Law 5) by posting an internal maintenance **contract** with their own crew. Sell energy under per-game-day **service-subscription contracts** to nearby producers (sawmills, smelters, clay quarries) — these are the same contract template a code-service uses, just delivering energy instead of code output. Spot energy is also posted on a small **order book** for buyers without a subscription. As player-built renewables or fuel competitors enter the region, the utility rebalances pricing.

**Revenue.** Subscription fees per game-day per subscribed customer, plus spot-market sales. Costs are mining labor + plant maintenance + decay. The structural moat is geographic — Law 4 sub-law (regional grids) means rivals must build a competing plant in the same region to take share.

**Why it works.** Energy *is* a material in the spec; "service subscription" is an existing contract template; regional-only delivery is just a movement constraint. No new primitive.

---

## Business 3 — Aegis Mutual (insurance underwriter, no physical footprint beyond a clerk's office)

**Primitives used:** Capital, Contracts, Markets (for re-pricing), Labor (light), Code (later, for pricing automation), Reputation surface (Law 7, exposed via the contract history primitive).

**Setup.** A single cheap inland **plot** for a small office. The owner holds a large pile of **capital** as a reserve. The product is an **insurance contract** — but "insurance" isn't a new contract template; it's the existing contract primitive parameterised with a premium clause and a payout clause. The party paying the premium gets a payout if a defined trigger fires.

**Daily activity.** Read the public contract market for shippers, lenders, and farmers needing protection. Underwrite tailor-made **contract proposals**: "You pay me X per game-day; if your supply-contract counterparty breaches, I pay you Y." Each policy is one contract. Maintain capital reserves above expected payouts. Track which counterparties keep getting insured against — if too much exposure piles up against a single shipper, renegotiate or refuse new policies. Settle claims when triggers fire (engine-enforced — payout is a contract clause, not a manual decision). Their public **reputation** (Law 7) shows every policy honored or breached, which is the single biggest sales driver.

**Revenue.** Premium income minus payouts minus reserve cost-of-capital. Profitable when their pricing of risk beats the market's pricing.

**Why it works.** Insurance is a *parameterised contract*, not a special primitive. Conservation holds — premiums move from insured → insurer; payouts move insurer → insured. No path to printing money.

---

## Business 4 — Anvil Recruiting (specialist staffing & training agency)

**Primitives used:** Labor, Contracts, Capital, Plots (training facility), Reputation, light Code (later, for matching).

**Setup.** A populated **plot** with a small training facility. Anvil doesn't extract or produce *anything physical* — its product is **labor** that already has a skill premium. They scout generic NPC laborers in the region's labor pool, hire them under one contract, train them at the facility (training is a **production** recipe whose output is "labor with raised skill" instead of a new material — same engine, different output type), then place them with paying clients under a separate **employment contract**.

**Daily activity.** Recruit: post hiring offers in the labor pool at slightly above market wages. Train: each trainee occupies a slot at the facility for N game-days, costing wages + facility decay maintenance. Place: when a player-run business posts a job needing skilled labor, Anvil offers a placement under a multi-month **employment contract** at a rate above generic market wages. Anvil collects a placement fee plus a margin on the wage spread. Watch their **reputation** — the public record of how many placed workers stayed vs. quit — because that's what lets them charge a premium.

**Revenue.** Placement fees + wage spread (client pays Anvil X per game-day per placed worker, Anvil pays the worker Y, keeps X − Y). When skilled labor is scarce, the spread widens.

**Why it works.** Labor is already first-class (Primitive 3). "Training" doesn't need its own primitive — it's a production recipe whose inputs are labor + capital + facility-time and whose output is *more skilled* labor. Conservation holds because skill is an attribute on labor, not a new conserved quantity.

---

## Business 5 — Tape & Tick Liquidity (market-making firm)

**Primitives used:** Capital (heavy), Markets (order books), Code (Phase 4+ for automation), light Plots/Labor.

**Setup.** One cheap **plot** to satisfy the "must exist somewhere" rule. A pile of **capital** is the entire production capacity. A handful of clerks (later, automated **code services**) post and refresh orders on multiple commodity **order books** — say clay, lumber, copper.

**Daily activity.** For each tracked asset, post simultaneous bid and ask **orders** straddling the current mid-price by a configurable spread. As the market moves, cancel and re-post (movement of capital between orders is free; only filled trades transfer value). When inventory of the asset accumulates from being lifted/hit too much on one side, widen the spread on the heavy side and tighten on the light side until inventory rebalances. Hedge inventory exposure via **contracts** with miners or processors when possible. Watch for fat-finger or one-sided flow from less informed players, lean into it.

**Revenue.** The bid-ask spread, scaled by daily volume traded through their book, minus inventory carrying cost (decay on perishables; opportunity cost on capital).

**Why it works.** Market-making is *heavy use* of two existing primitives (capital + markets), not a new primitive. The order-book primitive (7b) already models everything needed: place, cancel, fill, inventory. No new mechanics.

---

## Verdict (Phase 0 test gate)

All five businesses above compose cleanly from the existing 9 primitives. **No new primitive is required.**

Specifically:
- "Insurance" is a parameterised **contract**, not a new primitive.
- "Training" is a **production** recipe whose output is a labor-attribute change.
- "Service-subscription" (Hearthlight's energy contracts) re-uses the same contract template the Phase 4 code-service layer will use.
- "Market-making" is heavy use of **capital** + **markets**, not a new mechanic.
- Vertical integration is just two **production** stages on two **plots** linked by **movement**.

Combined with doc 03's five canonical examples (shipping, SaaS, bank, speculator, surveying firm), that's **10 distinct businesses** expressible in the current primitive set. The primitive set is good enough to leave Phase 0.

**Provisional pass on the test gate, pending an outside reader.** Per `13_PHASED_TODO.md`, the formal pass requires: someone other than the designer reads the descriptions and says "yes, you could actually run any of these in this game." That step is on Avi (or a friend / Shmuel) — once that confirmation lands, Phase 0 → Phase 1.
