# Realm Assets MCP Server

Generates PNG game assets for the Realm 2D economic sim, saving them directly
into the Godot project at `realm_client/assets/icons/`.

## Setup

```bash
cd realm_assets_mcp
pip install -r requirements.txt
```

Set your fal.ai API key (get one at [fal.ai](https://fal.ai)):

```bash
export FAL_KEY=your_fal_api_key
```

Or add to the repo root `.env` (gitignored):

```
FAL_KEY=your_fal_api_key
```

## Add to Cursor MCP config

Project config is at `.cursor/mcp.json`. After editing, restart MCP servers in
Cursor (Settings → MCP → refresh).

For a user-global config, use the same `mcpServers` block with an absolute `cwd`
path to `realm_assets_mcp/`.

## Generate everything (CLI)

From `realm_assets_mcp/` after `FAL_KEY` is set and [fal.ai billing](https://fal.ai/dashboard/billing) has credit:

```bash
python generate_all.py              # skip existing PNGs
python generate_all.py --only boats # vessel, small_vessel, boat aliases only
python generate_all.py --force      # regenerate all
```

Counts: 33 buildings, 68 materials (incl. boats), 13 terrain, 21 events, 26 UI (~161 images, ~$0.50 on Flux Schnell).

## Usage in Cursor

```
# See what's already generated
realm_list_assets("all")

# Get style reference before generating
realm_style_reference()

# Generate a specific icon
realm_generate_building_icon("strip_mine", variants=2)

# Bootstrap all building icons at once
realm_generate_batch("buildings")

# Custom one-off
realm_generate_custom("Margaux the merchant advisor, portrait", "custom/margaux.png", size=128)
```

## Output structure

```
realm_client/assets/icons/
├── buildings/      strip_mine.png, foundry.png, ...  (64×64)
├── materials/      coal.png, iron_ore.png, ...        (32×32)
├── terrain/        plains.png, mountain.png, ...      (64×64)
├── events/         drought.png, epidemic.png, ...     (32×32)
└── ui/             claim.png, build.png, trade.png    (24×24)
```

## API cost estimate

fal.ai Flux Schnell: ~$0.003 per image.
Full set (all categories, 1 variant each): ~$0.36 total.
With 2 variants to pick best: ~$0.72 total.

For final art, set `FAL_MODEL = "fal-ai/flux/dev"` in `config.py`.
