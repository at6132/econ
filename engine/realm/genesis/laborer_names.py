"""Phase 7B — procedural laborer name pool.

We combine 40 first names × 40 last names = 1,600 unique combinations,
plenty for several thousand laborer NPCs in a single save. Names are
deterministic given a seed (``world.rng`` derives from ``world.tick``).

Aesthetic target: spare, lived-in, slightly old-world — these are working
people in a four-island frontier economy. No fantasy flourishes, no
"Sir/Lady" titles, no fictional surnames. Period-neutral working names.
"""

from __future__ import annotations

import random

__all__ = ["FIRST_NAMES", "LAST_NAMES", "generate_laborer_name"]


FIRST_NAMES: tuple[str, ...] = (
    "Mara", "Tomas", "Elin", "Anders", "Hilde", "Jens", "Sigrid", "Otto",
    "Karin", "Edvard", "Greta", "Lars", "Asta", "Roland", "Liv", "Magnus",
    "Hedda", "Rune", "Maja", "Soren", "Britt", "Ivar", "Frida", "Knut",
    "Tora", "Oskar", "Inge", "Bjorn", "Saga", "Hakon", "Vera", "Linus",
    "Ada", "Pelle", "Nora", "Kasper", "Selma", "Halvard", "Mira", "Erik",
)


LAST_NAMES: tuple[str, ...] = (
    "Stenholm", "Halberg", "Vegg", "Eklund", "Tofte", "Skarrud", "Mellberg",
    "Lindqvist", "Bergstrand", "Kvist", "Hovde", "Saether", "Brodal",
    "Tranmael", "Holter", "Reinholt", "Vaage", "Dahlin", "Engebret",
    "Ekstrom", "Asplund", "Bratlie", "Solberg", "Wiken", "Sjogren",
    "Halvorsen", "Egeland", "Mehl", "Aamodt", "Lundeen", "Steiro",
    "Vinje", "Aune", "Ostrem", "Granli", "Tvedt", "Kjellberg", "Roald",
    "Hilden", "Bryn",
)


def generate_laborer_name(rng: random.Random) -> str:
    """Pick one first + one last name uniformly using the provided RNG."""
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
