# Realm engine

Authoritative Python simulation: tick-based, deterministic RNG, double-entry money, matter conservation on the transaction layer.

Run tests from this directory:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Run the HTTP API (stub for the Next.js client):

```bash
pip install -e .
uvicorn realm.api:app --reload --app-dir .
```

(`--app-dir .` keeps imports relative to `engine/` where `realm` lives.)
