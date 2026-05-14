from realm.world.biome_noise import terrain_for_cell
from realm.world.terrain import Terrain


def test_terrain_for_cell_deterministic() -> None:
    a = terrain_for_cell(77, 3, 9)
    b = terrain_for_cell(77, 3, 9)
    assert a is b


def test_terrain_for_cell_is_enum() -> None:
    t = terrain_for_cell(1, 0, 0)
    assert isinstance(t, Terrain)
