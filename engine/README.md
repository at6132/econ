# Realm engine

Authoritative Python simulation: tick-based, deterministic RNG, double-entry money, matter conservation on the transaction layer.

Run tests from this directory:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Run the HTTP API (from this `engine/` directory):

```bash
pip install -e .
uvicorn realm.api:app --reload --port 8000
```

The Next.js app in `../web` rewrites `/api/engine/*` to this server in dev.
