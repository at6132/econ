"""Technology eras, research labs, and party research progress."""

from realm.research.bonuses import research_output_multiplier
from realm.research.patents import (
    grant_patent,
    tick_era_advancement,
    tick_patent_licensing,
    tick_research_competition,
)
from realm.research.research_lab import (
    complete_research,
    party_research_summary,
    start_research,
    tick_research_progress,
)
from realm.research.tech_tree import ERAS, TECH_NODES, TechEraId, TechNodeId

__all__ = [
    "research_output_multiplier",
    "ERAS",
    "TECH_NODES",
    "TechEraId",
    "TechNodeId",
    "grant_patent",
    "tick_era_advancement",
    "tick_patent_licensing",
    "tick_research_competition",
    "complete_research",
    "party_research_summary",
    "start_research",
    "tick_research_progress",
]
