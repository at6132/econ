# Realm engine

Authoritative Python simulation: tick-based, deterministic RNG, double-entry money, matter conservation on the transaction layer.

Run tests from this directory:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Tier-3 Haiku agents (optional): install `pip install -e ".[llm]"`, set `ANTHROPIC_API_KEY`, then `python -m realm.llm_cli --party llm_margaux` or `POST /llm/step?party=llm_margaux`. Disable with `REALM_LLM_DISABLE=1`. Model override: `REALM_LLM_MODEL` (default `claude-3-5-haiku-20241022`).

Run the HTTP API (from this `engine/` directory):

```bash
pip install -e .
uvicorn realm.api:app --reload --port 8000
```

The Next.js app in `../web` rewrites `/api/engine/*` to this server in dev.
