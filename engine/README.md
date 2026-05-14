# Realm engine

Authoritative Python simulation: tick-based, deterministic RNG, double-entry money, matter conservation on the transaction layer.

**New here?** Read [ARCHITECTURE.md](./ARCHITECTURE.md) for the folder map, then [BEST_PRACTICES.md](./BEST_PRACTICES.md) for the rules every contributor follows.

Run tests from this directory:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest tests -n auto      # ~80s parallel; -v --tb=short for noise
```

Tier-3 Haiku (optional): `pip install -e ".[llm]"`, `ANTHROPIC_API_KEY`. Party ids are scenario-specific (e.g. frontier/millrace → `llm_margaux`, cartel → `llm_elira`). CLI: `python -m realm.llm_cli --party <id> --scenario <name>`. **Session spend cap:** `REALM_LLM_SESSION_CAP_USD` (default `2.0`); pricing estimates use `REALM_LLM_PRICE_INPUT_PER_MTOK_USD` / `OUTPUT`. Disable: `REALM_LLM_DISABLE=1`. Model: `REALM_LLM_MODEL` (default `claude-3-5-haiku-20241022`).

Run the HTTP API (from this `engine/` directory):

```bash
pip install -e .
uvicorn realm.api:app --reload --port 8000
```

The Next.js app in `../web` rewrites `/api/engine/*` to this server in dev.
