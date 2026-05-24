"""Load and query the merged lab preset catalog (featured + generated)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from realm.labs.preset_generator import generate_lab_presets
from realm.labs.preset_schema import LAB_CATEGORIES, LabCategory, LabPreset

_FEATURED_DIR = Path(__file__).resolve().parent / "presets" / "featured"


def _preset_from_dict(raw: dict[str, Any]) -> LabPreset:
    category = raw.get("category", "Strategy")
    if category not in LAB_CATEGORIES:
        category = "Strategy"
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return LabPreset(
        id=str(raw["id"]),
        title=str(raw["title"]),
        description=str(raw.get("description", "")),
        category=category,  # type: ignore[arg-type]
        tags=tuple(str(t) for t in tags),
        base=raw.get("base", "frontier"),  # type: ignore[arg-type]
        params=dict(raw.get("params") or {}),
        overlays={k: bool(v) for k, v in (raw.get("overlays") or {}).items()},
        defaults=dict(raw.get("defaults") or {}),
        featured=bool(raw.get("featured", True)),
    )


def _load_featured_presets() -> list[LabPreset]:
    if not _FEATURED_DIR.is_dir():
        return []
    out: list[LabPreset] = []
    for path in sorted(_FEATURED_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    out.append(_preset_from_dict(item))
        elif isinstance(data, dict):
            if "presets" in data:
                for item in data["presets"]:
                    if isinstance(item, dict):
                        out.append(_preset_from_dict(item))
            else:
                out.append(_preset_from_dict(data))
    return out


@lru_cache(maxsize=1)
def all_lab_presets() -> tuple[LabPreset, ...]:
    by_id: dict[str, LabPreset] = {}
    for p in generate_lab_presets():
        by_id[p.id] = p
    for p in _load_featured_presets():
        by_id[p.id] = p
    return tuple(sorted(by_id.values(), key=lambda x: (not x.featured, x.category, x.title)))


def get_lab_preset(preset_id: str) -> LabPreset:
    pid = preset_id.strip()
    for p in all_lab_presets():
        if p.id == pid:
            return p
    raise ValueError(f"unknown lab preset: {preset_id!r}")


def list_lab_presets(
    *,
    category: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    featured_only: bool = False,
    offset: int = 0,
    limit: int = 48,
) -> tuple[list[LabPreset], int]:
    items = list(all_lab_presets())
    if featured_only:
        items = [p for p in items if p.featured]
    if category:
        cat = category.strip()
        items = [p for p in items if p.category == cat]
    if tag:
        t = tag.strip().lower()
        items = [p for p in items if t in (x.lower() for x in p.tags)]
    if q:
        needle = q.strip().lower()
        items = [
            p
            for p in items
            if needle in p.id.lower()
            or needle in p.title.lower()
            or needle in p.description.lower()
            or any(needle in t.lower() for t in p.tags)
        ]
    total = len(items)
    page = items[offset : offset + limit]
    return page, total


def catalog_stats() -> dict[str, int]:
    presets = all_lab_presets()
    by_cat: dict[str, int] = {}
    for p in presets:
        by_cat[p.category] = by_cat.get(p.category, 0) + 1
    return {
        "total": len(presets),
        "featured": sum(1 for p in presets if p.featured),
        **{f"category_{k}": v for k, v in by_cat.items()},
    }
