# Realm web (Phase 1)

Next.js client for the solo prototype. The simulation runs in `../engine` (FastAPI on port 8000).

```bash
npm install
npm run dev
```

Dev proxy: requests to `/api/engine/*` rewrite to `http://127.0.0.1:8000/*`, so start the engine first:

```bash
cd ../engine
python -m pip install -e .
uvicorn realm.api:app --reload --port 8000
```
