# 12 — Risks and Mitigations

> Honest list of what can kill this project. Re-read every quarter. Update when something becomes more or less risky.

Format: **Risk → Why it matters → Mitigation → Tripwire (when to escalate)**

---

## Existential risks (could kill the entire project)

### R1. The core loop isn't fun in solo mode

**Why it matters:** Solo mode is the existence test. If a stranger doesn't enjoy 1 hour of solo, the design is broken. No amount of multiplayer or polish saves it.

**Mitigation:**
- Phase 1 ships an ugly playable solo prototype within ~2–3 months
- Mandatory playtest with 3–5 strangers before exiting Phase 1
- Willing to throw out 6 months of work if playtest reveals fundamental design failure

**Tripwire:** if 4 of 5 playtesters say "no, I would not keep playing," stop and rethink the primitives. Do not continue with broken design. *(This is the rule that protects you from yourself.)*

---

### R2. The user-code layer is too hard to build, too hard to use, or unsafe

**Why it matters:** The user-code layer is the moat. Without it, Realm is "another economy sim." With it, Realm is a platform.

**Mitigation:**
- Ship v1 *without* the user-code layer (Phase 1–3 don't depend on it)
- When user-code lands (Phase 4), start with block-based UI to keep the floor low
- Use Lua (mature, sandboxable) — don't build a custom language
- Have a small alpha cohort hammer the user-code layer before public release
- If sandbox security is broken, *yank the feature* until fixed; don't ship leaky code

**Tripwire:** if Phase 4 prototype shows that <30% of alpha players can build a useful service in a week, the UX is wrong. Iterate before exposing publicly.

---

### R3. Scope creep during the long pre-launch

**Why it matters:** This is a 5-year+ project. Scope creep is how 5 years becomes 10 years becomes never-shipping.

**Mitigation:**
- The phased TODO (doc 13) is the contract. New ideas go to a backlog, not into the current phase.
- Each phase has a hard test gate. Until passed, no phase advancement.
- Re-read pillars (doc 02) before adding any new feature.
- If you *must* add a feature, drop another from the same phase.

**Tripwire:** if a phase is running >50% over its time estimate without a release-ready milestone, *stop and assess*. Do not continue adding scope while behind schedule.

---

### R4. You burn out

**Why it matters:** Solo developer building a 5-year project. Burnout is a project-killer.

**Mitigation:**
- Phases are sized to ship something real every 3–6 months. Each phase is a win.
- Solo mode launching publicly (Phase 3) gives early external validation and possibly revenue.
- This project plays to your strengths (agents, economic systems, programmable infra) — leverage that
- Take the win at each phase. Don't internalize "I've shipped nothing until v1.0 final."

**Tripwire:** if you go more than 2 months without genuine momentum, take a real break. The project will still be there.

---

## High-impact risks (could cripple but not kill)

### R5. The economy hyperinflates / deflates / stagnates

**Why it matters:** Economic dysfunction makes the game un-fun fast. Hyperinflation breaks pricing signals. Deflation kills risk-taking. Stagnation is just boring.

**Mitigation:**
- Conservation laws strictly enforced (doc 04, Law 1)
- Money creation only through visible designed channels
- Telemetry on inflation rate, gini, market depth, etc.
- Solo mode and closed cohorts catch this before public mode
- Levers exist (NPC seed money rate, decay rates) — but use them sparingly

**Tripwire:** if inflation in a closed cohort exceeds 50% over a 30-day season, halt and audit. Some money sink is missing.

---

### R6. AI agents in solo mode aren't fun (too dumb or too smart)

**Why it matters:** Solo mode lives or dies on AI agent quality.

**Mitigation:**
- Tier 1 agents are deterministic and tunable
- Tier 3 (LLM) agents have curated personalities and difficulty profiles
- Per-scenario tuning of AI behavior
- Player can choose difficulty
- Iterate based on playtests

**Tripwire:** if playtests consistently say "the AI feels random / fake / boring," redesign agent strategies. This is fixable but requires real effort.

---

### R7. The mobile companion app is unused

**Why it matters:** Mobile is a lot of work. If players don't use it, that work was wasted.

**Mitigation:**
- Don't build mobile until solo mode is shipped and proven
- Design mobile around 5 specific flows (doc 10) — don't try to be a full client
- Push notifications for time-sensitive events drive engagement
- Mobile launches *after* there's something engaging to monitor (i.e., an active multiplayer shard)

**Tripwire:** if mobile DAU is <30% of web DAU after 60 days post-launch, reassess the value prop.

---

### R8. Multiplayer infrastructure is too expensive / unreliable

**Why it matters:** Persistent multiplayer is hard to operate. Downtime, lag, data loss are all common.

**Mitigation:**
- Don't open public multiplayer until closed cohorts have proven the architecture
- Determinism allows replay-from-snapshot for disaster recovery
- Monitor everything; alert on anything weird
- Start small (1 shard, ~100 players) before scaling

**Tripwire:** if any closed cohort has >2% data loss or >5 hours downtime per month, multiplayer isn't ready.

---

### R9. New players can't break in

**Why it matters:** If existing players have all the good plots and capital, no one new joins. Game dies on a slow timer.

**Mitigation:**
- Frontier zones (doc 11)
- Seasonal resets for some shards
- New-player starter packs
- Bootstrap-friendly first hour script (doc 08)

**Tripwire:** if new-player retention at day 7 is <20%, dig into what's blocking them.

---

### R10. Cheating / exploits in multiplayer

**Why it matters:** Players who exploit ruin the experience for everyone else.

**Mitigation:**
- Authoritative server (doc 04, Law 10)
- All actions go through validation
- Comprehensive audit log (deterministic engine = perfect replay)
- Reputation system penalizes detected exploits
- Harsh penalties for confirmed cheating (account lock + reset)

**Tripwire:** if a single exploit affects >5% of players' state, halt the shard, fix, restore from snapshot.

---

## Medium-impact risks

### R11. The 2D visual style alienates players who expected 3D

**Why it matters:** Some players will dismiss the game on screenshots alone.

**Mitigation:**
- Lean into the trading-platform aesthetic. Don't apologize for being 2D.
- Marketing emphasizes the *strategic* and *informational* aspects.
- Show, don't tell — clip of an engaging market crash, not a static screenshot.

**Tripwire:** if marketing CTR is consistently below industry baseline, revisit visual assets.

---

### R12. Monetization confusion

**Why it matters:** A free game that should be paid leaves money on the table; a paid game that should be free leaves players on the table.

**Mitigation:**
- Solo mode: one-time purchase (~$30–50). Maybe.
- Public multiplayer: subscription or season pass. Maybe.
- No play-to-earn / blockchain / token mechanics.
- No pay-to-win in multiplayer (cosmetic / convenience only).
- Defer monetization decisions until Phase 3 launch.

**Tripwire:** none yet — this is a Phase 3 decision.

---

### R13. Legal — gambling / financial regulation

**Why it matters:** When players trade in-game commodities, equities, derivatives, with real-money stakes (subscription), regulators may classify this as gambling or unregistered securities trading.

**Mitigation:**
- In-game currency is *not* convertible to real currency (no withdrawal mechanism)
- No real-world cash prizes for competitive seasons (consider digital goods only)
- TOS includes clear "this is a game, not financial advice, no real money" disclaimers
- Consult a lawyer before launching paid competitive seasons or tournaments
- Be especially careful in restrictive jurisdictions

**Tripwire:** if any regulator inquires, immediately seek legal counsel.

---

### R14. AI agent costs spiral (LLM bills)

**Why it matters:** Tier 3 agents cost real money. Many concurrent worlds = real bills.

**Mitigation:**
- Solo mode: agents only tick when player is actively playing (paused otherwise)
- Public mode: only ~5–10 named LLM agents per shard, slow tick rate
- Cache LLM responses aggressively where personality isn't changing
- Use cheaper models for some agent decisions (only the "creative" decisions need top-tier LLM)
- Monitor cost per active session; cap if needed

**Tripwire:** if LLM cost exceeds $0.50 per active solo-mode hour, optimize before scaling.

---

### R15. Community / moderation problems

**Why it matters:** Open multiplayer means abuse, harassment, in-game griefing.

**Mitigation:**
- Reputation system handles in-game griefing organically (cheaters get isolated)
- Out-of-game (chat, etc.) needs traditional moderation
- Hire / volunteer moderators before opening public multiplayer
- Clear TOS, clear enforcement, ban hammers ready

**Tripwire:** if community sentiment turns negative on public forums, intervene quickly.

---

## Lower-impact risks

### R16. Competing game launches first

**Why it matters:** If a competitor ships a similar concept before us, we lose first-mover advantage.

**Mitigation:**
- The user-code layer is unique and hard to copy
- Speed-to-market via solo-first strategy
- Strong design pillars = a differentiated product even if surface concept is shared

**Tripwire:** if a credible competitor ships, do not panic. Differentiation matters more than first-ness.

---

### R17. Documentation rot

**Why it matters:** This doc set will become stale unless maintained. A stale spec is worse than no spec.

**Mitigation:**
- Each phase ends with a spec update pass
- Glossary (doc 15) prevents term drift
- Re-read pillars (doc 02) every phase

**Tripwire:** if any team member notices spec contradictions, stop and resolve.

---

### R18. Solo-developer bus factor

**Why it matters:** You're building this alone (or with Shmuel). If something happens to you, the project ends.

**Mitigation:**
- Documentation. (This doc set is part of that.)
- Code is well-commented.
- Architecture is clean enough for a successor to understand.
- Consider open-sourcing parts of the engine eventually.

**Tripwire:** none specific — this is a long-term hygiene practice.

---

## Risks deliberately accepted (we're not mitigating these)

### A1. "What if it's not commercially successful?"

It might not be. We accept that. The project is worth doing because the design is interesting, it plays to our strengths, and even partial success is meaningful.

### A2. "What if the user-code layer changes the game in ways we can't predict?"

That's the point. Emergent design means surprising outcomes. We accept that some emergent dynamics will be unexpected — and we'll iterate.

### A3. "What if multiplayer never happens?"

Solo mode is a complete game. We can stop at solo mode and have shipped a real product.

---

## Quarterly risk review checklist

Re-read this doc every quarter. Update:
- New risks that have emerged
- Risks that have become less acute (delete or downgrade)
- Risks that have become more acute (escalate, plan response)
- Tripwires that have been hit (act on them)

A risk register is only useful if it's maintained.
