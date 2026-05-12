"""In-memory atlas cluster-tree access for the /api/atlas/labels endpoint.

The cluster tree (``atlas_cluster``) is small (~few thousand nodes per
projection) and immutable for a given projection, so we load it once
per process and serve viewport queries from RAM. The cost-per-request
of the SQL alternative ("scan all clusters that overlap this viewport,
binary-search on lambda") is wasteful when the entire dataset fits in
single-digit MB.

API:

    tree = get_tree(con, projection)        # cached
    clusters = tree.slice_for_viewport(viewport, target_count)
    # -> list[ClusterNode] (cluster_id, centroid, bbox, paper_count, ...)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import psycopg


@dataclass(frozen=True)
class ClusterNode:
    """One row of ``atlas_cluster`` mirrored in-process."""

    cluster_id: int
    parent_id: int | None
    lambda_birth: float
    lambda_death: float
    paper_count: int
    centroid_x: float
    centroid_y: float
    bbox_xmin: float
    bbox_ymin: float
    bbox_xmax: float
    bbox_ymax: float

    def bbox_intersects(self, viewport: tuple[float, float, float, float]) -> bool:
        vxmin, vymin, vxmax, vymax = viewport
        return not (
            self.bbox_xmax < vxmin
            or self.bbox_xmin > vxmax
            or self.bbox_ymax < vymin
            or self.bbox_ymin > vymax
        )


class ClusterTree:
    """Lambda-sliceable view over one projection's atlas_cluster rows."""

    def __init__(self, projection: str, nodes: list[ClusterNode]) -> None:
        self.projection = projection
        # Stable id-lookup map and sorted-lambda axis for binary search.
        self.nodes = nodes
        self.by_id: dict[int, ClusterNode] = {n.cluster_id: n for n in nodes}
        # Sorted distinct lambda values, used to step through plausible
        # slicing levels in target-count binary search.
        births = sorted({n.lambda_birth for n in nodes})
        deaths = sorted({n.lambda_death for n in nodes})
        self._lambda_axis: list[float] = sorted(set(births + deaths))

    def slice_at_lambda(self, lambda_val: float) -> list[ClusterNode]:
        """Return the partition of clusters "alive" at ``lambda_val``.

        A cluster is alive if ``lambda_birth <= lambda_val < lambda_death``.
        The root cluster (lambda_birth=0) covers lambda_val=0 and is
        returned as the single partition at the lowest lambda. At very
        high lambda (above the tree's max death) the slice is empty.
        """
        out: list[ClusterNode] = []
        for n in self.nodes:
            if n.lambda_birth <= lambda_val < n.lambda_death:
                out.append(n)
        return out

    def slice_for_viewport(
        self,
        viewport: tuple[float, float, float, float],
        target_count: int,
    ) -> list[ClusterNode]:
        """Find a slice with approximately ``target_count`` clusters
        whose bbox intersects ``viewport``.

        Algorithm: binary search over the sorted distinct lambda values.
        At each candidate lambda L:
          n = #(clusters alive at L) whose bbox intersects viewport
        We seek the largest L such that n >= target_count (deeper zoom →
        more, smaller clusters). Caveat: at the very deepest lambda the
        slice is empty, so we also clamp.

        Returns the slice itself (sorted by paper_count desc so the FE
        gets the largest/most-visible labels first).
        """
        axis = self._lambda_axis
        if not axis:
            return []

        def count_at(L: float) -> tuple[int, list[ClusterNode]]:
            slice_ = self.slice_at_lambda(L)
            visible = [n for n in slice_ if n.bbox_intersects(viewport)]
            return len(visible), visible

        # Binary search over the lambda axis.
        lo, hi = 0, len(axis) - 1
        best: list[ClusterNode] = []
        best_diff = float("inf")
        while lo <= hi:
            mid = (lo + hi) // 2
            L = axis[mid]
            cnt, visible = count_at(L)
            # Track the slice whose count is closest to target_count.
            diff = abs(cnt - target_count)
            if diff < best_diff or (diff == best_diff and cnt >= target_count):
                best_diff = diff
                best = visible
            if cnt < target_count:
                # Need finer clusters → higher lambda → larger axis index.
                lo = mid + 1
            elif cnt > target_count:
                # Too many → coarser → lower lambda.
                hi = mid - 1
            else:
                break

        # Sort by descending paper_count: the FE renders top-down, and
        # larger clusters dominate the visual footprint.
        best.sort(key=lambda n: n.paper_count, reverse=True)
        return best


# Process-local cache. The tree is read-only and rebuilt only when the
# operator re-runs scripts/build_atlas_clusters.py, so a stale process
# (which would still serve labels from yesterday's tree until a restart)
# is an explicit and acceptable trade.
_tree_cache: dict[str, ClusterTree] = {}
_tree_cache_lock = threading.Lock()


def _load_tree(con: psycopg.Connection[Any], projection: str) -> ClusterTree:
    nodes: list[ClusterNode] = []
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT cluster_id, parent_id, lambda_birth, lambda_death,
                   paper_count, centroid_x, centroid_y,
                   bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax
            FROM atlas_cluster
            WHERE projection = %s
            """,
            [projection],
        )
        for row in cur.fetchall():
            nodes.append(
                ClusterNode(
                    cluster_id=int(row[0]),
                    parent_id=int(row[1]) if row[1] is not None else None,
                    lambda_birth=float(row[2]),
                    lambda_death=float(row[3]),
                    paper_count=int(row[4]),
                    centroid_x=float(row[5]),
                    centroid_y=float(row[6]),
                    bbox_xmin=float(row[7]),
                    bbox_ymin=float(row[8]),
                    bbox_xmax=float(row[9]),
                    bbox_ymax=float(row[10]),
                )
            )
    return ClusterTree(projection, nodes)


def get_tree(con: psycopg.Connection[Any], projection: str) -> ClusterTree:
    """Return the cached cluster tree for ``projection``, loading on first use."""
    with _tree_cache_lock:
        cached = _tree_cache.get(projection)
        if cached is not None:
            return cached
        tree = _load_tree(con, projection)
        _tree_cache[projection] = tree
        return tree


def invalidate_cache(projection: str | None = None) -> None:
    """Drop the cached tree(s). Call after re-running the build script."""
    with _tree_cache_lock:
        if projection is None:
            _tree_cache.clear()
        else:
            _tree_cache.pop(projection, None)
