"""
Generate all Realm icon assets via fal.ai Flux Schnell.
Skips files that already exist. Run from realm_assets_mcp/:

    python generate_all.py
    python generate_all.py --force   # regenerate everything
    python generate_all.py --only materials,boats
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from config import (
    BUILDING_DIR,
    DEFAULT_SIZES,
    EVENT_DIR,
    MATERIAL_DIR,
    TERRAIN_DIR,
    UI_DIR,
    ensure_asset_dirs,
    load_env,
)
from generator import generate_asset
from prompts import (
    BUILDING_PROMPTS,
    EVENT_PROMPTS,
    MATERIAL_PROMPTS,
    TERRAIN_PROMPTS,
    UI_PROMPTS,
)

# Boat aliases: same PNG used for multiple ids (engine only has vessel + small_vessel)
BOAT_ALIASES: dict[str, str] = {
    "boat": "vessel",
    "cargo_ship": "vessel",
    "fishing_boat": "small_vessel",
}


async def _gen_one(
    prompt: str,
    dest: Path,
    size: int,
    *,
    force: bool,
) -> str:
    if dest.exists() and not force:
        return "skip"
    await generate_asset(prompt, dest, size=size, num_images=1)
    return "ok"


async def _run_category(
    name: str,
    catalog: dict[str, str],
    out_dir: Path,
    size: int,
    *,
    force: bool,
) -> tuple[int, int, int, list[str]]:
    ok = skip = fail = 0
    errors: list[str] = []
    for key, prompt in sorted(catalog.items()):
        dest = out_dir / f"{key}.png"
        try:
            status = await _gen_one(prompt, dest, size, force=force)
            if status == "skip":
                skip += 1
            else:
                ok += 1
                print(f"  + {name}/{key}.png")
        except Exception as e:
            fail += 1
            errors.append(f"{key}: {e}")
            print(f"  ! {name}/{key}: {e}", file=sys.stderr)
    return ok, skip, fail, errors


async def _copy_boat_aliases(*, force: bool) -> int:
    """Copy generated boat PNGs to alias filenames."""
    import shutil

    copied = 0
    for alias, source in BOAT_ALIASES.items():
        src = MATERIAL_DIR / f"{source}.png"
        dst = MATERIAL_DIR / f"{alias}.png"
        if not src.is_file():
            continue
        if dst.exists() and not force and dst.stat().st_mtime >= src.stat().st_mtime:
            continue
        shutil.copy2(src, dst)
        copied += 1
        print(f"  = materials/{alias}.png <- {source}.png")
    return copied


async def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all Realm game icons")
    parser.add_argument("--force", action="store_true", help="Regenerate even if PNG exists")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated: buildings,materials,terrain,events,ui,boats",
    )
    args = parser.parse_args()
    load_env()

    ensure_asset_dirs()

    only = {x.strip().lower() for x in args.only.split(",") if x.strip()}
    run_all = not only

    categories: list[tuple[str, dict[str, str], Path, int]] = []
    if run_all or "buildings" in only:
        categories.append(("buildings", BUILDING_PROMPTS, BUILDING_DIR, DEFAULT_SIZES["building"]))
    if run_all or "materials" in only or "boats" in only:
        mats = dict(MATERIAL_PROMPTS)
        if "boats" in only and "materials" not in only:
            boat_keys = {"vessel", "small_vessel", "boat", "cargo_ship", "fishing_boat"}
            mats = {k: v for k, v in mats.items() if k in boat_keys}
        categories.append(("materials", mats, MATERIAL_DIR, DEFAULT_SIZES["material"]))
    if run_all or "terrain" in only:
        categories.append(("terrain", TERRAIN_PROMPTS, TERRAIN_DIR, DEFAULT_SIZES["terrain"]))
    if run_all or "events" in only:
        categories.append(("events", EVENT_PROMPTS, EVENT_DIR, DEFAULT_SIZES["event"]))
    if run_all or "ui" in only:
        categories.append(("ui", UI_PROMPTS, UI_DIR, DEFAULT_SIZES["ui"]))

    total_ok = total_skip = total_fail = 0
    all_errors: list[str] = []

    for name, catalog, out_dir, size in categories:
        n = len(catalog)
        print(f"\n[{name}] {n} assets @ {size}px …")
        ok, skip, fail, errs = await _run_category(
            name, catalog, out_dir, size, force=args.force
        )
        total_ok += ok
        total_skip += skip
        total_fail += fail
        all_errors.extend(errs)
        print(f"  done: {ok} generated, {skip} skipped, {fail} failed")

    if run_all or "boats" in only or "materials" in only:
        print("\n[boats] copying aliases …")
        copied = await _copy_boat_aliases(force=args.force)
        print(f"  {copied} alias copies")

    print(
        f"\nTotal: {total_ok} generated, {total_skip} skipped, {total_fail} failed"
    )
    if all_errors:
        print("\nFailures:", file=sys.stderr)
        for e in all_errors[:20]:
            print(f"  {e}", file=sys.stderr)
        if len(all_errors) > 20:
            print(f"  … and {len(all_errors) - 20} more", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
