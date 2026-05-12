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
        max_size_ratio: float = 8.0,
    ) -> list[ClusterNode]:
        """Find ~target_count viewport-intersecting clusters of roughly
        similar size.

        Why not just bisect on lambda? HDBSCAN's condensed tree on this
        corpus is *unbalanced* at low lambda: one root cluster holds
        ~99% of points and the rest are tiny noise-eaten fringes. A
        single-lambda slice at small target_count gives you "1 huge
        cluster + (target_count - 1) tiny leaves" which is useless as
        labels. So instead, we do a top-down recursive split:

        1. Start with the slice at lambda=0 (the root), filtered to
           viewport-intersecting nodes. Same effect: typically just
           the root.
        2. Repeatedly take the *largest* cluster in the current slice
           and replace it with its viewport-intersecting children.
           Stop when either:
             a. We have >= target_count clusters AND the size-ratio
                between largest and smallest in the slice is <=
                max_size_ratio.
             b. The largest cluster has no further children (we hit
                a leaf — no more splitting possible).
             c. We've hit a hard cap of 4 * target_count to prevent
                runaway expansion in pathological trees.

        This guarantees that no single cluster dominates the label
        layer by ~100x.

        Returns the slice sorted by paper_count desc so the FE renders
        the most visually-dominant labels first.
        """
        if not self.nodes:
            return []

        # Children-of map (computed once and stashed; the slice loop
        # below does O(target_count) lookups, so amortised it's fine).
        children = self._children_map()

        # Start at the root(s). The root has parent_id=None. There may
        # be more than one root if HDBSCAN found disjoint top-level
        # density blobs (rare but possible), so we union them.
        roots = [n for n in self.nodes if n.parent_id is None]
        if not roots:
            # No root — pick the smallest cluster_id as a fallback.
            roots = [min(self.nodes, key=lambda n: n.cluster_id)]

        current: list[ClusterNode] = [n for n in roots if n.bbox_intersects(viewport)]
        if not current:
            # Root doesn't intersect viewport — fall back to all
            # viewport-intersecting nodes at lambda=0.
            current = [n for n in self.nodes if n.bbox_intersects(viewport)]
        if not current:
            return []

        # Two stop conditions. The harder cap exists so a pathological
        # tree (very long unsplittable chain) can't run away. Pick the
        # smaller of "target_count + a generous margin" and "10x
        # target_count"; both grow with target_count so users can dial
        # the slider up sensibly.
        hard_cap = min(max(target_count * 5, target_count + 16), 200)

        def imbalance_ratio(slice_: list[ClusterNode]) -> float:
            sizes = [c.paper_count for c in slice_ if c.paper_count > 0]
            if not sizes:
                return float("inf")
            return max(sizes) / min(sizes)

        # Walk: always split the largest cluster, until either (a) we
        # have >= target_count AND ratio fits, or (b) hard_cap, or (c)
        # the largest cluster is unsplittable in this viewport AND can't
        # find any other splittable cluster.
        while True:
            current.sort(key=lambda n: n.paper_count, reverse=True)
            ratio = imbalance_ratio(current)
            if len(current) >= target_count and ratio <= max_size_ratio:
                break
            if len(current) >= hard_cap:
                break

            # Try to split the largest cluster first. If it's a leaf in
            # the viewport (no intersecting children), walk down the
            # list to find one we *can* split.
            split_idx = None
            split_kids: list[ClusterNode] = []
            for i, c in enumerate(current):
                kids = [
                    k
                    for k in children.get(c.cluster_id, [])
                    if k.bbox_intersects(viewport)
                ]
                if kids:
                    split_idx = i
                    split_kids = kids
                    break
            if split_idx is None:
                # Nothing left to split.
                break
            current = current[:split_idx] + current[split_idx + 1 :] + split_kids

        current.sort(key=lambda n: n.paper_count, reverse=True)
        # Soft trim if we materially overshot the target. We keep the
        # *largest* clusters because they're the visually-dominant ones
        # — better to show the user 6 prominent labels than 18 small
        # ones at default slider value. The user can dial up the
        # density slider to surface more.
        if len(current) > target_count + max(2, target_count // 2):
            current = current[:target_count]
        return current

    def _children_map(self) -> dict[int, list[ClusterNode]]:
        """Build cluster_id -> direct children list. Cached on the tree."""
        cached = getattr(self, "_children_cache", None)
        if cached is not None:
            return cached
        out: dict[int, list[ClusterNode]] = {}
        for n in self.nodes:
            if n.parent_id is None:
                continue
            out.setdefault(n.parent_id, []).append(n)
        self._children_cache = out
        return out


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
