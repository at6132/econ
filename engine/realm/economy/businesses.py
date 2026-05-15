"""Phase 10C — business entities (organizational wrapper, no extra production path)."""

from __future__ import annotations

from dataclasses import dataclass, field

from realm.core.ids import PartyId, PlotId

__all__ = [
    "BusinessEntity",
    "BusinessTemplate",
    "BUSINESS_TEMPLATES",
]


@dataclass(frozen=True, slots=True)
class BusinessEntity:
    business_id: str
    owner_party: PartyId
    business_name: str
    business_type_tag: str
    description: str
    registered_at_tick: int
    registered_plot_ids: tuple[PlotId, ...]
    sub_account_label: str
    status: str
    suspension_reason: str | None
    public_profile: bool
    last_viability_check_tick: int


@dataclass(frozen=True, slots=True)
class BusinessTemplate:
    template_id: str
    display_name: str
    type_tag: str
    description: str
    suggested_buildings: tuple[str, ...]
    suggested_recipes: tuple[str, ...]
    why_viable: str
    example_revenue: str


BUSINESS_TEMPLATES: dict[str, BusinessTemplate] = {
    "coal_miner": BusinessTemplate(
        template_id="coal_miner",
        display_name="Coal miner",
        type_tag="mining",
        description="Extract coal, sell to exchange and local fuel demand.",
        suggested_buildings=("strip_mine",),
        suggested_recipes=("mine_coal",),
        why_viable="Energy demand pays for extraction.",
        example_revenue="Exchange + B2B coal listings.",
    ),
    "foundry": BusinessTemplate(
        template_id="foundry",
        display_name="Foundry",
        type_tag="foundry",
        description="Smelt ore into ingots and wire.",
        suggested_buildings=("foundry",),
        suggested_recipes=("smelt_iron", "draw_copper_wire"),
        why_viable="Metal premiums over raw ore.",
        example_revenue="Sell ingots undercutting exchange.",
    ),
    "shipping_company": BusinessTemplate(
        template_id="shipping_company",
        display_name="Shipping company",
        type_tag="shipping",
        description="Dock + vessel; register routes after traffic appears.",
        suggested_buildings=("dock",),
        suggested_recipes=tuple(),
        why_viable="Per-tile fees on busy lanes.",
        example_revenue="Route operator fees to cash:biz account.",
    ),
    "general_store": BusinessTemplate(
        template_id="general_store",
        display_name="General store",
        type_tag="retail",
        description="Stock grain, coal, bread for laborers.",
        suggested_buildings=("store",),
        suggested_recipes=tuple(),
        why_viable="Daily laborer foot traffic.",
        example_revenue="Retail markup on staples.",
    ),
    "grain_farm": BusinessTemplate(
        template_id="grain_farm",
        display_name="Grain farm",
        type_tag="farming",
        description="Grain row + gristmill chain.",
        suggested_buildings=("grain_row", "gristmill"),
        suggested_recipes=("grow_grain", "mill_grain"),
        why_viable="Food is always liquid.",
        example_revenue="Grain and flour listings.",
    ),
    "tool_manufacturer": BusinessTemplate(
        template_id="tool_manufacturer",
        display_name="Tool manufacturer",
        type_tag="tools",
        description="Tool workshop outputs picks and saws.",
        suggested_buildings=("tool_workshop",),
        suggested_recipes=("assemble_pick_axe",),
        why_viable="High margin durable goods.",
        example_revenue="Tool sell orders.",
    ),
    "surveying_firm": BusinessTemplate(
        template_id="surveying_firm",
        display_name="Surveying firm",
        type_tag="surveying",
        description="Survey plots and sell reports.",
        suggested_buildings=("field_stockade",),
        suggested_recipes=tuple(),
        why_viable="Knowledge sells as intel listings.",
        example_revenue="Survey report resale.",
    ),
    "bank": BusinessTemplate(
        template_id="bank",
        display_name="Bank",
        type_tag="banking",
        description="Loan and deposit products via contracts.",
        suggested_buildings=("bank_building",),
        suggested_recipes=tuple(),
        why_viable="Interest spread.",
        example_revenue="Loan repayments.",
    ),
    "apothecary": BusinessTemplate(
        template_id="apothecary",
        display_name="Apothecary",
        type_tag="apothecary",
        description="Medicine from wild herbs.",
        suggested_buildings=("apothecary",),
        suggested_recipes=("make_medicine",),
        why_viable="Health-driven demand spikes.",
        example_revenue="Medicine retail.",
    ),
    "research_lab": BusinessTemplate(
        template_id="research_lab",
        display_name="Research laboratory",
        type_tag="research_lab",
        description="Discover reactions and novel materials.",
        suggested_buildings=("laboratory",),
        suggested_recipes=tuple(),
        why_viable="Patent-like recipe discovery.",
        example_revenue="Sell scarce outputs.",
    ),
    "land_developer": BusinessTemplate(
        template_id="land_developer",
        display_name="Land developer",
        type_tag="land_developer",
        description="Claim, improve, flip plots.",
        suggested_buildings=("residence",),
        suggested_recipes=tuple(),
        why_viable="Plot appreciation.",
        example_revenue="Plot listings after upgrade.",
    ),
    "construction_firm": BusinessTemplate(
        template_id="construction_firm",
        display_name="Construction firm",
        type_tag="construction_firm",
        description="Take construction orders; pivot like any NPC.",
        suggested_buildings=("residence",),
        suggested_recipes=tuple(),
        why_viable="Quoted labor + materials margin.",
        example_revenue="Escrow releases on completion.",
    ),
}
