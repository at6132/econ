"""
Realm Assets MCP Server — stdio transport.
Cursor calls these tools to generate PNGs directly into the Godot project.
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from config import (
    ASSETS_ROOT,
    BUILDING_DIR,
    DEFAULT_SIZES,
    EVENT_DIR,
    GODOT_ROOT,
    MATERIAL_DIR,
    STYLE_BASE,
    TERRAIN_DIR,
    UI_DIR,
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

load_env()

mcp = FastMCP(
    "realm-assets",
    instructions=(
        "Generate PNG game assets for the Realm 2D economic simulation game. "
        "Assets are saved directly to the Godot project at realm_client/assets/icons/. "
        "Always call realm_list_assets first to see what already exists before generating. "
        "Use realm_generate_building_icon for buildings, realm_generate_material_icon "
        "for resources, realm_generate_terrain_tile for terrain, etc."
    ),
)


@mcp.tool(
    description=(
        "Generate a building icon PNG for a Realm blueprint. "
        "Saves to realm_client/assets/icons/buildings/{blueprint_id}.png at 64×64px. "
        "blueprint_id must be a valid Realm building ID (strip_mine, foundry, etc). "
        "Set variants=2 or 3 to generate multiple options and pick the best. "
        "Returns the file path(s) of saved assets."
    )
)
async def realm_generate_building_icon(
    blueprint_id: str,
    variants: int = 1,
    custom_prompt: str = "",
) -> dict:
    """Generate a 64×64 building icon for the blueprint sidebar."""
    prompt = custom_prompt or BUILDING_PROMPTS.get(
        blueprint_id, f"{blueprint_id.replace('_', ' ')} building"
    )
    out_path = BUILDING_DIR / f"{blueprint_id}.png"
    size = DEFAULT_SIZES["building"]
    try:
        paths = await generate_asset(prompt, out_path, size=size, num_images=variants)
        return {
            "ok": True,
            "blueprint_id": blueprint_id,
            "paths": [str(p) for p in paths],
            "godot_path": f"res://assets/icons/buildings/{blueprint_id}.png",
            "prompt_used": prompt,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "blueprint_id": blueprint_id}


@mcp.tool(
    description=(
        "Generate a material/resource icon PNG for Realm's inventory and bazaar. "
        "Saves to realm_client/assets/icons/materials/{material_id}.png at 32×32px. "
        "material_id examples: coal, iron_ore, iron_ingot, lumber, grain, electricity. "
        "Returns the file path of the saved asset."
    )
)
async def realm_generate_material_icon(
    material_id: str,
    variants: int = 1,
    custom_prompt: str = "",
) -> dict:
    """Generate a 32×32 material/resource icon."""
    prompt = custom_prompt or MATERIAL_PROMPTS.get(
        material_id, f"{material_id.replace('_', ' ')} resource material"
    )
    out_path = MATERIAL_DIR / f"{material_id}.png"
    size = DEFAULT_SIZES["material"]
    try:
        paths = await generate_asset(prompt, out_path, size=size, num_images=variants)
        return {
            "ok": True,
            "material_id": material_id,
            "paths": [str(p) for p in paths],
            "godot_path": f"res://assets/icons/materials/{material_id}.png",
            "prompt_used": prompt,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "material_id": material_id}


@mcp.tool(
    description=(
        "Generate a terrain tile texture for the Realm world map plot grid. "
        "Saves to realm_client/assets/icons/terrain/{terrain_type}.png at 64×64px. "
        "terrain_type: plains, forest, mountain, hills, desert, tundra, coastal, valley, swamp, tropical. "
        "These replace the flat color fills in PlotGridView."
    )
)
async def realm_generate_terrain_tile(
    terrain_type: str,
    variants: int = 1,
    custom_prompt: str = "",
) -> dict:
    """Generate a 64×64 terrain tile texture."""
    prompt = custom_prompt or TERRAIN_PROMPTS.get(
        terrain_type, f"{terrain_type} terrain aerial view texture tile"
    )
    out_path = TERRAIN_DIR / f"{terrain_type}.png"
    size = DEFAULT_SIZES["terrain"]
    try:
        paths = await generate_asset(prompt, out_path, size=size, num_images=variants)
        return {
            "ok": True,
            "terrain_type": terrain_type,
            "paths": [str(p) for p in paths],
            "godot_path": f"res://assets/icons/terrain/{terrain_type}.png",
            "prompt_used": prompt,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "terrain_type": terrain_type}


@mcp.tool(
    description=(
        "Generate a world event icon for the Chronicle feed and map overlays. "
        "Saves to realm_client/assets/icons/events/{event_type}.png at 32×32px. "
        "event_type examples: drought, epidemic, storm, mine_collapse, flood, boom_town. "
        "These appear as map indicators and in the Chronicle world feed."
    )
)
async def realm_generate_event_icon(
    event_type: str,
    variants: int = 1,
    custom_prompt: str = "",
) -> dict:
    """Generate a 32×32 world event icon."""
    prompt = custom_prompt or EVENT_PROMPTS.get(
        event_type, f"{event_type.replace('_', ' ')} disaster warning symbol"
    )
    out_path = EVENT_DIR / f"{event_type}.png"
    size = DEFAULT_SIZES["event"]
    try:
        paths = await generate_asset(prompt, out_path, size=size, num_images=variants)
        return {
            "ok": True,
            "event_type": event_type,
            "paths": [str(p) for p in paths],
            "godot_path": f"res://assets/icons/events/{event_type}.png",
            "prompt_used": prompt,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "event_type": event_type}


@mcp.tool(
    description=(
        "Generate a UI icon for Realm's interface elements. "
        "Saves to realm_client/assets/icons/ui/{name}.png at 24×24px. "
        "name examples: claim, survey, build, produce, ship, trade, hire, finance. "
        "These replace emoji in nav buttons and action controls."
    )
)
async def realm_generate_ui_icon(
    name: str,
    variants: int = 1,
    custom_prompt: str = "",
) -> dict:
    """Generate a 24×24 UI icon."""
    prompt = custom_prompt or UI_PROMPTS.get(
        name, f"{name.replace('_', ' ')} action button icon, minimal"
    )
    out_path = UI_DIR / f"{name}.png"
    size = DEFAULT_SIZES["ui"]
    try:
        paths = await generate_asset(prompt, out_path, size=size, num_images=variants)
        return {
            "ok": True,
            "name": name,
            "paths": [str(p) for p in paths],
            "godot_path": f"res://assets/icons/ui/{name}.png",
            "prompt_used": prompt,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "name": name}


@mcp.tool(
    description=(
        "Generate all missing icons for a category in one call. "
        "category: 'buildings', 'materials', 'terrain', 'events', or 'ui'. "
        "Skips icons that already exist on disk. "
        "Returns a summary of what was generated and what was skipped. "
        "Use this to bootstrap a full category at once."
    )
)
async def realm_generate_batch(category: str) -> dict:
    """Generate all missing icons for a category."""
    catalog: dict[str, str]
    out_dir: Path
    size: int

    if category == "buildings":
        catalog, out_dir, size = BUILDING_PROMPTS, BUILDING_DIR, DEFAULT_SIZES["building"]
    elif category == "materials":
        catalog, out_dir, size = MATERIAL_PROMPTS, MATERIAL_DIR, DEFAULT_SIZES["material"]
    elif category == "terrain":
        catalog, out_dir, size = TERRAIN_PROMPTS, TERRAIN_DIR, DEFAULT_SIZES["terrain"]
    elif category == "events":
        catalog, out_dir, size = EVENT_PROMPTS, EVENT_DIR, DEFAULT_SIZES["event"]
    elif category == "ui":
        catalog, out_dir, size = UI_PROMPTS, UI_DIR, DEFAULT_SIZES["ui"]
    else:
        return {
            "ok": False,
            "error": f"unknown category '{category}'. Use: buildings, materials, terrain, events, ui",
        }

    generated: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for key, prompt in catalog.items():
        dest = out_dir / f"{key}.png"
        if dest.exists():
            skipped.append(key)
            continue
        try:
            await generate_asset(prompt, dest, size=size, num_images=1)
            generated.append(key)
        except Exception as e:
            failed.append({"key": key, "error": str(e)})

    return {
        "ok": True,
        "category": category,
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "summary": (
            f"Generated {len(generated)}, skipped {len(skipped)} existing, {len(failed)} failed"
        ),
    }


@mcp.tool(
    description=(
        "List all existing generated assets in a category. "
        "Call this before generating to avoid regenerating existing assets. "
        "category: 'buildings', 'materials', 'terrain', 'events', 'ui', or 'all'. "
        "Returns file names and Godot resource paths."
    )
)
def realm_list_assets(category: str = "all") -> dict:
    """List existing generated assets."""
    dirs: dict[str, Path] = {
        "buildings": BUILDING_DIR,
        "materials": MATERIAL_DIR,
        "terrain": TERRAIN_DIR,
        "events": EVENT_DIR,
        "ui": UI_DIR,
    }
    result: dict[str, list[dict]] = {}
    if category == "all":
        targets = dirs
    elif category in dirs:
        targets = {category: dirs[category]}
    else:
        return {"ok": False, "error": f"unknown category '{category}'"}
    for cat, d in targets.items():
        if not d.exists():
            result[cat] = []
            continue
        result[cat] = [
            {
                "name": f.stem,
                "path": str(f),
                "godot_path": f"res://assets/icons/{cat}/{f.name}",
                "size_kb": round(f.stat().st_size / 1024, 1),
            }
            for f in sorted(d.glob("*.png"))
        ]
    total = sum(len(v) for v in result.values())
    return {"ok": True, "assets": result, "total": total}


@mcp.tool(
    description=(
        "Generate a completely custom asset with a full prompt. "
        "Use when the pre-defined categories don't cover the needed asset. "
        "Provide the full descriptive prompt (style base is auto-prepended). "
        "size: pixel dimension (16, 24, 32, 48, 64, 128). "
        "output_filename: relative to realm_client/assets/icons/ e.g. 'custom/my_icon.png'. "
        "Returns the saved path and Godot resource path."
    )
)
async def realm_generate_custom(
    prompt: str,
    output_filename: str,
    size: int = 64,
    variants: int = 1,
) -> dict:
    """Generate a custom asset with a fully specified prompt."""
    assets_root = ASSETS_ROOT.resolve()
    out_path = (assets_root / output_filename).resolve()
    try:
        out_path.relative_to(assets_root)
    except ValueError:
        return {"ok": False, "error": "output_filename must be inside assets/icons/"}
    try:
        paths = await generate_asset(prompt, out_path, size=size, num_images=variants)
        godot_rel = str(out_path.relative_to(GODOT_ROOT.resolve())).replace("\\", "/")
        return {
            "ok": True,
            "paths": [str(p) for p in paths],
            "godot_path": f"res://{godot_rel}",
            "prompt_used": prompt,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool(
    description=(
        "Return the current Realm art style configuration: palette, style base prompt, "
        "available categories, and directory layout. "
        "Read this before generating assets to understand the visual language."
    )
)
def realm_style_reference() -> dict:
    """Return the art style configuration for Realm assets."""
    return {
        "palette": {
            "background": "#0c0612 (deep dark purple — icons sit on this)",
            "gold_accent": "#FFD84A",
            "cyan_magic": "#6EE7FF",
            "warm_text": "#F4EAD8",
            "ok_green": "#7BED9F",
            "danger_red": "#FF6B6B",
        },
        "aesthetic": (
            "Top-down 2D economic civilisation sim. Medieval/industrial fantasy era. "
            "Dark, sophisticated, not cartoonish. Think aged parchment maps and trade ledgers. "
            "Icons should be warm-toned, painterly, with dark outlines. "
            "Clear silhouette at 32×32. Transparent background always."
        ),
        "style_base_prompt": STYLE_BASE,
        "categories": {
            "buildings": "64×64 — building icons for blueprint sidebar",
            "materials": "32×32 — resource/material icons for inventory and bazaar",
            "terrain": "64×64 — tile textures for plot grid view",
            "events": "32×32 — world event icons for chronicle and map",
            "ui": "24×24 — action and nav button icons",
        },
        "total_assets_defined": {
            "buildings": len(BUILDING_PROMPTS),
            "materials": len(MATERIAL_PROMPTS),
            "terrain": len(TERRAIN_PROMPTS),
            "events": len(EVENT_PROMPTS),
            "ui": len(UI_PROMPTS),
        },
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
