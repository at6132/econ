"""SQLite persistence for solo saves (one row = one snapshot)."""

from __future__ import annotations

import sqlite3

from realm.state_io import dumps_json, loads_json
from realm.world import World


def save_snapshot(path: str, world: World) -> None:
    payload = dumps_json(world)
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS realm_save (id INTEGER PRIMARY KEY CHECK (id = 1), json TEXT NOT NULL)"
        )
        con.execute("INSERT OR REPLACE INTO realm_save (id, json) VALUES (1, ?)", (payload,))
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
