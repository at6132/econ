"""SQLite persistence for solo saves.

Schema: ``realm_save`` keeps the serialized World as a single row (``id = 1``),
``realm_save_meta`` is a sidecar key/value table so the Continue menu can show
``tick``, ``scenario_id``, ``seed`` and ``saved_at`` without deserializing the
JSON blob. Older saves without the meta table still load — meta keys are best
effort, so absence yields empty values.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from realm.api.serialization import dumps_json, loads_json
from realm.world import World


_META_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS realm_save_meta ("
    "k TEXT PRIMARY KEY, v TEXT NOT NULL"
    ")"
)


def save_snapshot(path: str, world: World) -> None:
    """Persist ``world`` to ``path`` (single-slot SQLite file). Also writes meta."""
    payload = dumps_json(world)
    saved_at = int(time.time())
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS realm_save ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL"
            ")"
        )
        con.execute(_META_TABLE_DDL)
        con.execute("INSERT OR REPLACE INTO realm_save (id, json) VALUES (1, ?)", (payload,))
        meta_rows = [
            ("tick", str(int(world.tick))),
            ("scenario_id", str(world.scenario_id)),
            ("seed", str(int(world.seed))),
            ("saved_at", str(saved_at)),
            ("world_id", str(getattr(world, "world_id", "") or "")),
            ("world_name", str(getattr(world, "world_name", "") or "")),
        ]
        for k, v in meta_rows:
            con.execute("INSERT OR REPLACE INTO realm_save_meta (k, v) VALUES (?, ?)", (k, v))
        con.commit()
    finally:
        con.close()


def load_snapshot(path: str) -> World:
    con = sqlite3.connect(path)
    try:
        row = con.execute("SELECT json FROM realm_save WHERE id = 1").fetchone()
        if row is None:
            raise FileNotFoundError("no save in database")
        return loads_json(row[0])
    finally:
        con.close()


def read_meta(path: str) -> dict[str, Any]:
    """Return ``{tick, scenario_id, seed, saved_at, world_id, world_name}`` from meta.

    Tolerant of older saves that pre-date the meta table — returns empty
    strings/zeros for fields that aren't present.
    """
    out: dict[str, Any] = {
        "tick": 0,
        "scenario_id": "",
        "seed": 0,
        "saved_at": 0,
        "world_id": "",
        "world_name": "",
    }
    try:
        con = sqlite3.connect(path)
    except sqlite3.Error:
        return out
    try:
        try:
            rows = con.execute("SELECT k, v FROM realm_save_meta").fetchall()
        except sqlite3.Error:
            return out
        m: dict[str, str] = {str(k): str(v) for (k, v) in rows}
        out["tick"] = int(m.get("tick", "0") or 0)
        out["scenario_id"] = m.get("scenario_id", "")
        out["seed"] = int(m.get("seed", "0") or 0)
        out["saved_at"] = int(m.get("saved_at", "0") or 0)
        out["world_id"] = m.get("world_id", "")
        out["world_name"] = m.get("world_name", "")
    finally:
        con.close()
    return out
