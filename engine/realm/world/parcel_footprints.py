"""Parcel footprint shapes for worldgen — single source of truth for deed geometry.

Each deed is a **connected set of world-map tiles** (1 hectare per tile).
Footprints are polyominoes: rectangles, lines, L-shapes, T/plus, zigzags (S/Z).

``Plot.world_cells`` stores absolute ``(x, y)`` coordinates. Area and build-grid
size derive from :mod:`realm.world.plot_scale` (tile count × constants).
"""

from __future__ import annotations

from typing import Any, Final

MAX_PARCEL_CELLS: Final[int] = 9

# Weighted base shapes (normalized to min corner). Variants include rotation + mirror.
_CATALOG: list[tuple[frozenset[tuple[int, int]], float]] = []


def _norm(cells: set[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    if not cells:
        return frozenset()
    min_x = min(c[0] for c in cells)
    min_y = min(c[1] for c in cells)
    return frozenset((x - min_x, y - min_y) for x, y in cells)


def _rect(w: int, h: int) -> frozenset[tuple[int, int]]:
    return _norm({(x, y) for x in range(w) for y in range(h)})


def _build_catalog() -> list[tuple[frozenset[tuple[int, int]], float]]:
    if _CATALOG:
        return _CATALOG
    items: list[tuple[frozenset[tuple[int, int]], float]] = [
        (_rect(1, 1), 0.10),
        (_rect(2, 1), 0.09),
        (_rect(1, 2), 0.09),
        (_rect(3, 1), 0.06),
        (_rect(1, 3), 0.06),
        (_rect(2, 2), 0.14),
        (_rect(3, 2), 0.08),
        (_rect(2, 3), 0.07),
        (_rect(3, 3), 0.05),
        # L tromino (3 cells)
        (_norm({(0, 0), (0, 1), (1, 0)}), 0.07),
        # L pentomino (5 cells)
        (_norm({(0, 0), (0, 1), (0, 2), (1, 2)}), 0.06),
        (_norm({(0, 0), (1, 0), (2, 0), (2, 1)}), 0.05),
        # Zigzag / S tetromino
        (_norm({(0, 0), (1, 0), (1, 1), (2, 1)}), 0.06),
        (_norm({(0, 1), (1, 1), (1, 0), (2, 0)}), 0.05),
        # T pentomino
        (_norm({(0, 0), (1, 0), (2, 0), (1, 1)}), 0.04),
        # Plus
        (_norm({(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)}), 0.03),
        # Thin bent / stair (5 cells, not a rectangle)
        (_norm({(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)}), 0.04),
        (_norm({(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)}), 0.04),
    ]
    _CATALOG.extend(items)
    return _CATALOG


def _rotate90(fp: frozenset[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    if not fp:
        return fp
    max_x = max(c[0] for c in fp)
    return _norm({(y, max_x - x) for x, y in fp})


def _mirror_x(fp: frozenset[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    if not fp:
        return fp
    max_x = max(c[0] for c in fp)
    return _norm({(max_x - x, y) for x, y in fp})


def footprint_variants(base: frozenset[tuple[int, int]]) -> list[frozenset[tuple[int, int]]]:
    """All rotations and mirrors (deduped)."""
    out: list[frozenset[tuple[int, int]]] = []
    seen: set[frozenset[tuple[int, int]]] = set()
    cur = base
    for _ in range(4):
        for fp in (cur, _mirror_x(cur)):
            if fp not in seen and 1 <= len(fp) <= MAX_PARCEL_CELLS:
                seen.add(fp)
                out.append(fp)
        cur = _rotate90(cur)
    return out


def pick_weighted_footprint(rng: Any) -> frozenset[tuple[int, int]]:
    catalog = _build_catalog()
    roll = rng.random()
    acc = 0.0
    total = sum(wt for _, wt in catalog)
    for fp, wt in catalog:
        acc += wt / total
        if roll <= acc:
            return fp
    return _rect(1, 1)


def footprint_fits(
    assigned: list[list[str | None]],
    anchor_x: int,
    anchor_y: int,
    footprint: frozenset[tuple[int, int]],
    width: int,
    height: int,
) -> bool:
    for dx, dy in footprint:
        x = anchor_x + dx
        y = anchor_y + dy
        if x >= width or y >= height:
            return False
        if assigned[y][x] is not None:
            return False
    return True


def stamp_footprint(
    assigned: list[list[str | None]],
    anchor_x: int,
    anchor_y: int,
    footprint: frozenset[tuple[int, int]],
    pid: str,
) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    for dx, dy in footprint:
        x = anchor_x + dx
        y = anchor_y + dy
        assigned[y][x] = pid
        cells.append((x, y))
    return cells


def pick_footprint_at(
    rng: Any,
    assigned: list[list[str | None]],
    anchor_x: int,
    anchor_y: int,
    width: int,
    height: int,
) -> frozenset[tuple[int, int]]:
    """Try several random shapes; prefer larger fits for variety."""
    best: frozenset[tuple[int, int]] | None = None
    for _ in range(14):
        base = pick_weighted_footprint(rng)
        for variant in footprint_variants(base):
            if footprint_fits(assigned, anchor_x, anchor_y, variant, width, height):
                if best is None or len(variant) > len(best):
                    best = variant
    if best is not None:
        return best
    return frozenset({(0, 0)})


def _cells_connected(cells: set[tuple[int, int]]) -> bool:
    if not cells:
        return False
    start = next(iter(cells))
    seen: set[tuple[int, int]] = {start}
    frontier = [start]
    while frontier:
        x, y = frontier.pop()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in cells and (nx, ny) not in seen:
                seen.add((nx, ny))
                frontier.append((nx, ny))
    return len(seen) == len(cells)


def classify_parcel_shape(cells: tuple[tuple[int, int], ...] | frozenset[tuple[int, int]]) -> str:
    """``mono`` | ``line`` | ``rect`` | ``l`` | ``zigzag`` | ``t`` | ``plus`` | ``poly``."""
    if isinstance(cells, frozenset):
        s = set(cells)
    else:
        s = set(cells)
    n = len(s)
    if n <= 1:
        return "mono"
    if not _cells_connected(s):
        return "poly"
    xs = [c[0] for c in s]
    ys = [c[1] for c in s]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max_x - min_x + 1
    h = max_y - min_y + 1
    bbox_area = w * h
    if n == bbox_area:
        if w == 1 or h == 1:
            return "line"
        return "rect"
    if n == bbox_area - 1:
        return "l"

    def _match_template(template: frozenset[tuple[int, int]]) -> bool:
        for variant in footprint_variants(template):
            for ox in range(min_x - 3, min_x + 4):
                for oy in range(min_y - 3, min_y + 4):
                    shifted = {(x + ox, y + oy) for x, y in variant}
                    if shifted == s:
                        return True
        return False

    if _match_template(_norm({(0, 0), (1, 0), (1, 1), (2, 1)})):
        return "zigzag"
    if _match_template(_norm({(0, 0), (1, 0), (2, 0), (1, 1)})):
        return "t"
    if _match_template(_norm({(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)})):
        return "plus"
    return "poly"


def carve_l_corners(
    plots: dict[Any, Any],
    assigned: list[list[str | None]],
    rng: Any,
    *,
    chance: float = 0.22,
) -> None:
    """Post-pass: transfer a corner tile between adjacent rectangular deeds to form L-shapes."""
    from realm.core.ids import PlotId

    pids = list(plots.keys())
    order = list(range(len(pids)))
    for i in range(len(order) - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        order[i], order[j] = order[j], order[i]

    for idx in order:
        if rng.random() > chance:
            continue
        pid = pids[idx]
        plot = plots[pid]
        cells = list(plot.world_cells)
        if len(cells) < 4:
            continue
        s = set(cells)
        xs = [c[0] for c in s]
        ys = [c[1] for c in s]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max_x - min_x + 1
        h = max_y - min_y + 1
        if len(s) != w * h:
            continue

        corners = [
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]
        for i in range(len(corners) - 1, 0, -1):
            j = int(rng.random() * (i + 1))
            corners[i], corners[j] = corners[j], corners[i]
        for cx, cy in corners:
            carved = s - {(cx, cy)}
            if len(carved) != w * h - 1:
                continue
            if not _cells_connected(carved):
                continue
            neighbor = _neighbor_plot_at(cx, cy, pid, assigned, plots)
            if neighbor is None:
                continue
            nplot = plots[neighbor]
            ns = set(nplot.world_cells)
            grown = ns | {(cx, cy)}
            if not _cells_connected(grown):
                continue
            assigned[cy][cx] = str(neighbor)
            plot.world_cells = tuple(carved)
            nplot.world_cells = tuple(grown)
            plot.parcel_shape = classify_parcel_shape(plot.world_cells)
            nplot.parcel_shape = classify_parcel_shape(nplot.world_cells)
            break


def _neighbor_plot_at(
    x: int,
    y: int,
    from_pid: Any,
    assigned: list[list[str | None]],
    plots: dict[Any, Any],
) -> Any | None:
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if ny < 0 or ny >= len(assigned) or nx < 0 or nx >= len(assigned[0]):
            continue
        other = assigned[ny][nx]
        if other is not None and other != str(from_pid):
            from realm.core.ids import PlotId

            return PlotId(other)
    return None
