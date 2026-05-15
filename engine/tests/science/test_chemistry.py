"""Phase 10E — chemistry catalog."""

from realm.materials import MATERIALS
from realm.science.chemistry import ELEMENT_SYMBOLS, REACTIONS_PUBLIC, try_reaction


def test_element_count_and_reactions_reference_materials() -> None:
    assert len(ELEMENT_SYMBOLS) == 49
    assert len(REACTIONS_PUBLIC) >= 35
    keys = {str(m) for m in MATERIALS}
    for row in REACTIONS_PUBLIC:
        out = str(row["output"])
        assert out in keys, out
        for inp in row["inputs"]:
            assert str(inp) in keys, inp


def test_try_reaction_sand_coal() -> None:
    assert try_reaction("sand", "coal") == ("glass", 1)
