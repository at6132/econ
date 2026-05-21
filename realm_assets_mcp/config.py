"""
Realm Assets MCP — configuration.
"""
from __future__ import annotations

import os
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).parent.parent
GODOT_ROOT = REPO_ROOT / "realm_client"
ASSETS_ROOT = GODOT_ROOT / "assets" / "icons"

# Output directories (created on first use)
BUILDING_DIR = ASSETS_ROOT / "buildings"
MATERIAL_DIR = ASSETS_ROOT / "materials"
TERRAIN_DIR = ASSETS_ROOT / "terrain"
EVENT_DIR = ASSETS_ROOT / "events"
UI_DIR = ASSETS_ROOT / "ui"
BLUEPRINT_DIR = ASSETS_ROOT / "blueprints"

# Default sizes per category
DEFAULT_SIZES: dict[str, int] = {
    "building": 64,
    "material": 32,
    "terrain": 64,
    "event": 32,
    "ui": 24,
    "blueprint": 64,
}

# Generation model
FAL_MODEL = "fal-ai/flux/schnell"
FAL_STEPS = 4
FAL_GUIDANCE = 3.5

# Style base — prepended to every prompt
STYLE_BASE = (
    "top-down 2D strategy game icon, isolated on transparent background, "
    "medieval industrial fantasy aesthetic, warm aged parchment tones with dark "
    "outlines, painterly texture, clear readable silhouette, game asset style, "
    "no text, no watermark, no border, centered composition"
)


def load_env() -> None:
    """Load FAL_KEY from repo .env if not already set."""
    if os.environ.get("FAL_KEY"):
        return
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not value:
            continue
        norm = key.lower().replace(".", "").replace("_", "")
        if key in ("FAL_KEY", "FAL_API_KEY", "fal.aikey") or norm in ("falkey", "falaikey"):
            os.environ["FAL_KEY"] = value
            return


def load_fal_key_from_env() -> None:
    """Alias for ``load_env`` (used by generator)."""
    load_env()


def ensure_asset_dirs() -> None:
    for d in (
        BUILDING_DIR,
        MATERIAL_DIR,
        TERRAIN_DIR,
        EVENT_DIR,
        UI_DIR,
        BLUEPRINT_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
