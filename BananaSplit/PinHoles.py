# Copyright (c) 2026 meteozond.
# This tool is released under the terms of the AGPLv3 or higher.

# Pin hole placement for split models. Plain geometry without Cura imports.
# Coordinates follow the Cura scene: Y is up and the build plate, which is also the cut plane, is y = 0.

from shapely.geometry import MultiLineString, Point, Polygon
from shapely.ops import polygonize, polylabel, unary_union
from typing import List, Tuple

import numpy
import trimesh

try:
    from shapely import contains_xy
except ImportError:
    # Shapely 1.x, bundled with older Cura
    contains_xy = None

# Section points get rounded so segment ends shared by neighboring triangles match exactly for polygonize.
# 4 decimals is 0.1 micron, far below printer resolution.
SNAP_DECIMALS = 4
# Grid points sampled over the section. More points place holes more evenly but slow every k-means step.
GRID_SAMPLE_COUNT = 3000
# Fixed number of Lloyd steps without a convergence check. Centers settle well before that for this sample count.
KMEANS_ITERATIONS = 100
# Finest grid step and placement precision in mm. Finer is invisible in print and only costs time.
RESOLUTION = 0.1


def cutSectionSolids(vertices: numpy.ndarray, faces: numpy.ndarray) -> List[Polygon]:
    """Solid regions of the mesh cross section at the cut plane, as polygons in the (x, z) plane."""
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    segments = trimesh.intersections.mesh_plane(mesh, plane_normal=[0, 1, 0], plane_origin=[0, 0, 0])
    if len(segments) == 0:
        return []
    segments_xz = numpy.round(segments[:, :, [0, 2]], SNAP_DECIMALS)
    enclosed = list(polygonize(unary_union(MultiLineString([tuple(map(tuple, s)) for s in segments_xz]))))

    # polygonize returns every enclosed area, including the insides of holes. Even-odd nesting tells them apart.
    outlines = [Polygon(area.exterior) for area in enclosed]
    solids = []
    for area in enclosed:
        probe = area.representative_point()
        depth = sum(1 for outline in outlines if outline.contains(probe)) - 1
        if depth % 2 == 0:
            solids.append(area)
    return solids


def _samplesInside(region, count: int) -> numpy.ndarray:
    """Grid points inside the region, roughly count of them."""
    min_x, min_y, max_x, max_y = region.bounds
    step = max(numpy.sqrt(region.area / count), RESOLUTION)
    xs, ys = numpy.meshgrid(numpy.arange(min_x, max_x + step, step), numpy.arange(min_y, max_y + step, step))
    xs, ys = xs.ravel(), ys.ravel()
    if contains_xy is not None:
        inside = contains_xy(region, xs, ys)
    else:
        inside = numpy.array([region.contains(Point(x, y)) for x, y in zip(xs, ys)], dtype=bool)
    return numpy.stack([xs[inside], ys[inside]], axis=1)


def _kMeans(samples: numpy.ndarray, count: int) -> numpy.ndarray:
    """Lloyd's k-means seeded by farthest point sampling, so the result is deterministic."""
    seeds = [int(numpy.argmax(numpy.linalg.norm(samples - samples.mean(axis=0), axis=1)))]
    distance = numpy.linalg.norm(samples - samples[seeds[0]], axis=1)
    while len(seeds) < count:
        seeds.append(int(numpy.argmax(distance)))
        distance = numpy.minimum(distance, numpy.linalg.norm(samples - samples[seeds[-1]], axis=1))
    centers = samples[seeds].copy()
    for _ in range(KMEANS_ITERATIONS):
        labels = numpy.argmin(numpy.linalg.norm(samples[:, None] - centers[None], axis=2), axis=1)
        centers = numpy.array(
            [samples[labels == k].mean(axis=0) if numpy.any(labels == k) else centers[k] for k in range(count)]
        )
    # A cluster mean can fall outside a non-convex region, so snap each center to its nearest sample
    return samples[numpy.argmin(numpy.linalg.norm(samples[:, None] - centers[None], axis=2), axis=0)]


def pinHoleCenters(
    solids: List[Polygon], count: int, hole_radius: float, wall_margin: float
) -> List[Tuple[float, float]]:
    """Up to count hole centers spread evenly over the whole cross section, with wall_margin around each hole."""
    if count < 1:
        return []
    region = unary_union([solid.buffer(-(hole_radius + wall_margin)) for solid in solids])
    if region.is_empty:
        return []
    if count == 1:
        largest = max(getattr(region, "geoms", [region]), key=lambda p: p.area)
        return [polylabel(largest, tolerance=RESOLUTION).coords[0]]

    samples = _samplesInside(region, GRID_SAMPLE_COUNT)
    if len(samples) < count:
        return [p.representative_point().coords[0] for p in getattr(region, "geoms", [region])][:count]

    # Two radii plus a wall between them, or neighboring holes would merge.
    # Holes that come closer get dropped when the section is too small for count.
    min_distance = 2 * hole_radius + wall_margin
    centers = []
    for center in _kMeans(samples, count):
        if all(numpy.linalg.norm(center - other) >= min_distance for other in centers):
            centers.append(center)
    return [tuple(c) for c in centers]


def cylinder(radius: float, half_height: float, segments: int = 32) -> Tuple[numpy.ndarray, numpy.ndarray]:
    """Closed cylinder along Y centered on the origin. Returns (vertices, triangle indices)."""
    angles = numpy.linspace(0, 2 * numpy.pi, segments, endpoint=False)
    ring = numpy.stack([radius * numpy.cos(angles), numpy.zeros(segments), radius * numpy.sin(angles)], axis=1)
    bottom = ring + [0, -half_height, 0]
    top = ring + [0, half_height, 0]
    vertices = numpy.vstack([bottom, top, [[0, -half_height, 0], [0, half_height, 0]]]).astype(numpy.float32)

    bottom_center, top_center = 2 * segments, 2 * segments + 1
    indices = []
    for i in range(segments):
        j = (i + 1) % segments
        indices.append([i, segments + i, j])
        indices.append([j, segments + i, segments + j])
        indices.append([bottom_center, i, j])
        indices.append([top_center, segments + j, segments + i])
    return vertices, numpy.asarray(indices, dtype=numpy.int32)
