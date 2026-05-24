"""Combinatorial lab preset generator — stable ids from templates × parameter lattice."""

from __future__ import annotations

from realm.core.player_economy import PLAYER_STARTING_CASH_CENTS
from realm.labs.preset_schema import LabCategory, LabPreset

# Frontier grid ladder (width, height)
_FRONTIER_GRIDS: tuple[tuple[int, int], ...] = (
    (8, 6),
    (12, 9),
    (16, 12),
    (20, 15),
    (24, 18),
    (32, 24),
)

# Genesis mini grids
_GENESIS_GRIDS: tuple[tuple[int, int], ...] = (
    (24, 18),
    (32, 24),
    (40, 30),
    (48, 36),
    (64, 48),
    (80, 60),
)

_CASH_TIERS: tuple[tuple[str, int], ...] = (
    ("broke", 100_000),
    ("tight", 485_000),
    ("normal", PLAYER_STARTING_CASH_CENTS),
    ("rich", 2_050_000),
)

_SETTLER_DENSITIES: tuple[tuple[str, int], ...] = (
    ("sparse", 0),
    ("light", 5),
    ("medium", 12),
    ("dense", 25),
    ("crowded", 45),
)

_CATEGORY_FOR_TEMPLATE: dict[str, LabCategory] = {
    "micro_frontier": "Strategy",
    "cartel_micro": "Markets",
    "bootstrapper_lab": "Strategy",
    "speculator_lab": "Stress",
    "millrace_lab": "Production",
    "micro_genesis": "Social",
    "genesis_tutorial": "Tutorial",
    "stress_frontier": "Stress",
    "market_frontier": "Markets",
}


def _slug(*parts: str) -> str:
    return "_".join(p.replace("-", "_") for p in parts if p)


def generate_lab_presets() -> list[LabPreset]:
    out: list[LabPreset] = []

    for w, h in _FRONTIER_GRIDS:
        for cash_name, cash_cents in _CASH_TIERS:
            pid = _slug("gen", "micro_frontier", f"{w}x{h}", cash_name)
            out.append(
                LabPreset(
                    id=pid,
                    title=f"Micro Frontier {w}×{h} · {cash_name.title()}",
                    description=(
                        f"Compact {w}×{h} frontier grid with ${cash_cents // 100:,} "
                        "starting cash — test claim, produce, and trade loops quickly."
                    ),
                    category="Strategy",
                    tags=("frontier", "micro", cash_name, f"{w}x{h}"),
                    base="frontier",
                    params={
                        "grid_width": w,
                        "grid_height": h,
                        "starting_cash_cents": cash_cents,
                        "scenario_id": "frontier",
                    },
                    featured=False,
                )
            )

    for w, h in _FRONTIER_GRIDS:
        if w < 16:
            continue
        for cash_name, cash_cents in _CASH_TIERS:
            pid = _slug("gen", "cartel_micro", f"{w}x{h}", cash_name)
            out.append(
                LabPreset(
                    id=pid,
                    title=f"Cartel Micro {w}×{h} · {cash_name.title()}",
                    description=(
                        f"Split grain market pressure on a {w}×{h} map — "
                        "study vendor vs pool pricing under cartel overlay."
                    ),
                    category="Markets",
                    tags=("cartel", "grain", "micro", cash_name, f"{w}x{h}"),
                    base="frontier",
                    params={
                        "grid_width": w,
                        "grid_height": h,
                        "starting_cash_cents": cash_cents,
                        "scenario_id": "cartel",
                    },
                    overlays={"cartel_grain": True},
                    featured=False,
                )
            )

    for w, h in ((24, 18), (32, 24), (40, 30)):
        pid = _slug("gen", "bootstrapper_lab", f"{w}x{h}")
        out.append(
            LabPreset(
                id=pid,
                title=f"Bootstrapper {w}×{h}",
                description="Tight cash, smaller map — survival-first expansion lab.",
                category="Strategy",
                tags=("bootstrapper", "tight", f"{w}x{h}"),
                base="frontier",
                params={
                    "grid_width": w,
                    "grid_height": h,
                    "starting_cash_cents": 485_000,
                    "scenario_id": "bootstrapper",
                },
                featured=False,
            )
        )

    for w, h in ((32, 24), (40, 30), (48, 36)):
        for label, cash in (("speculator", 2_050_000), ("millrace", 975_000), ("archive", 1_080_000)):
            sid = label
            pid = _slug("gen", f"{label}_lab", f"{w}x{h}")
            out.append(
                LabPreset(
                    id=pid,
                    title=f"{label.title()} {w}×{h}",
                    description=f"{label.title()} scenario parameters on a {w}×{h} lab grid.",
                    category=_CATEGORY_FOR_TEMPLATE.get(f"{label}_lab", "Stress"),
                    tags=(label, f"{w}x{h}"),
                    base="frontier",
                    params={
                        "grid_width": w,
                        "grid_height": h,
                        "starting_cash_cents": cash,
                        "scenario_id": sid,
                    },
                    featured=False,
                )
            )

    for w, h in _GENESIS_GRIDS:
        for dens_name, settlers in _SETTLER_DENSITIES:
            pid = _slug("gen", "micro_genesis", f"{w}x{h}", dens_name)
            out.append(
                LabPreset(
                    id=pid,
                    title=f"Genesis Mini {w}×{h} · {dens_name.title()}",
                    description=(
                        f"Population economy sandbox — {settlers} settlers at boot on "
                        f"a {w}×{h} continental layout."
                    ),
                    category="Social",
                    tags=("genesis", "population", dens_name, f"{w}x{h}"),
                    base="genesis",
                    params={
                        "grid_width": w,
                        "grid_height": h,
                        "settler_count": settlers,
                        "map_layout": "auto",
                    },
                    featured=False,
                )
            )

    for w, h in ((12, 9), (16, 12), (24, 18)):
        pid = _slug("gen", "genesis_tutorial", f"{w}x{h}")
        out.append(
            LabPreset(
                id=pid,
                title=f"Genesis Tutorial {w}×{h}",
                description="Tiny genesis map with a handful of settlers — learn towns and stores.",
                category="Tutorial",
                tags=("tutorial", "genesis", f"{w}x{h}"),
                base="genesis",
                params={
                    "grid_width": w,
                    "grid_height": h,
                    "settler_count": 8,
                    "map_layout": "continent",
                },
                defaults={"sim_speed": 1},
                featured=False,
            )
        )

    for w, h in _FRONTIER_GRIDS:
        pid = _slug("gen", "stress_frontier", f"{w}x{h}", "broke")
        out.append(
            LabPreset(
                id=pid,
                title=f"Stress Test {w}×{h}",
                description="Minimal cash on a tight grid — stress liquidity and input stalls.",
                category="Stress",
                tags=("stress", "broke", f"{w}x{h}"),
                base="frontier",
                params={
                    "grid_width": w,
                    "grid_height": h,
                    "starting_cash_cents": 50_000,
                    "scenario_id": "frontier",
                },
                featured=False,
            )
        )

    for w, h in ((16, 12), (24, 18), (32, 24)):
        pid = _slug("gen", "market_frontier", f"{w}x{h}", "rich")
        out.append(
            LabPreset(
                id=pid,
                title=f"Market Lab {w}×{h}",
                description="Well-funded player on a mid-size map — focus on order books and arbitrage.",
                category="Markets",
                tags=("markets", "rich", f"{w}x{h}"),
                base="frontier",
                params={
                    "grid_width": w,
                    "grid_height": h,
                    "starting_cash_cents": 5_000_000,
                    "scenario_id": "frontier",
                },
                featured=False,
            )
        )

    for w, h in _FRONTIER_GRIDS:
        for cash_name, cash_cents in _CASH_TIERS:
            pid = _slug("gen", "uniform_frontier", f"{w}x{h}", cash_name)
            out.append(
                LabPreset(
                    id=pid,
                    title=f"Uniform Grid {w}×{h} · {cash_name.title()}",
                    description=(
                        f"Regular {w}×{h} parcel grid — predictable geometry for "
                        "schematic and routing experiments."
                    ),
                    category="Production",
                    tags=("uniform", "frontier", cash_name, f"{w}x{h}"),
                    base="frontier",
                    params={
                        "grid_width": w,
                        "grid_height": h,
                        "starting_cash_cents": cash_cents,
                        "scenario_id": "frontier",
                        "uniform_plots": True,
                    },
                    featured=False,
                )
            )

    for w, h in _GENESIS_GRIDS:
        for cash_name, cash_cents in (("starter", 10_000_000), ("modest", 2_000_000), ("flush", 8_000_000)):
            for dens_name, settlers in _SETTLER_DENSITIES[:3]:
                pid = _slug("gen", "genesis_cash", f"{w}x{h}", dens_name, cash_name)
                out.append(
                    LabPreset(
                        id=pid,
                        title=f"Genesis {w}×{h} · {dens_name} · {cash_name}",
                        description=(
                            f"Social economy lab — {settlers} settlers, "
                            f"${cash_cents // 100:,} player cash."
                        ),
                        category="Social",
                        tags=("genesis", dens_name, cash_name, f"{w}x{h}"),
                        base="genesis",
                        params={
                            "grid_width": w,
                            "grid_height": h,
                            "settler_count": settlers,
                            "player_starting_cash_cents": cash_cents,
                            "map_layout": "auto",
                        },
                        featured=False,
                    )
                )

    for w, h in ((8, 6), (12, 9), (16, 12)):
        for sid in ("frontier", "cartel", "bootstrapper"):
            pid = _slug("gen", "quick", sid, f"{w}x{h}")
            cash = 485_000 if sid == "bootstrapper" else PLAYER_STARTING_CASH_CENTS
            out.append(
                LabPreset(
                    id=pid,
                    title=f"Quick {sid.title()} {w}×{h}",
                    description=f"Fast-boot {sid} ruleset on the smallest practical {w}×{h} map.",
                    category="Tutorial" if sid == "frontier" else "Markets",
                    tags=("quick", sid, f"{w}x{h}"),
                    base="frontier",
                    params={
                        "grid_width": w,
                        "grid_height": h,
                        "starting_cash_cents": cash,
                        "scenario_id": sid,
                    },
                    overlays={"cartel_grain": sid == "cartel"},
                    featured=False,
                )
            )

    return out
