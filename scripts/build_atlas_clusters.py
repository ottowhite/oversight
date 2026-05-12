"""Build the HDBSCAN cluster tree for an atlas projection.

For a given ``--projection`` (e.g. ``pacmap_pl_v1``, ``pacmap_v1``) this
script:

1. Pulls every paper that has both a halfvec embedding and a row in
   ``paper_projection_2d`` for that projection.
2. Reduces the 3072-d halfvec embeddings to 50 dims via PCA
   (``random_state=42`` for determinism).
3. Runs HDBSCAN on the 50-d representation. **Not** on the 2D PaCMAP
   coords — those are lossy and would group unrelated things that
   happen to project close. min_cluster_size=15 by default.
4. Walks the *condensed tree* — every node becomes one row in
   ``atlas_cluster``. Each node's ``lambda_birth`` is the lambda at which
   it splits from its parent; ``lambda_death`` is the lambda at which it
   in turn dissolves into noise (or splits into children).
5. For each cluster, computes centroid + 5/95 percentile bbox from
   members' 2D coords (queried from ``paper_projection_2d``).
6. Builds a c-TF-IDF sidecar: for every cluster's titles + first 200
   chars of abstract, counts unigram/bigram terms and persists the
   global per-term document frequency into ``atlas_cluster_term_idf``.

Idempotent: re-running for the same projection deletes prior rows and
re-populates from scratch.

Usage
-----

    uv run --with hdbscan --with scikit-learn --with pgvector \\
           --with "psycopg[binary]" --with python-dotenv \\
        python scripts/build_atlas_clusters.py \\
            --projection pacmap_pl_v1 \\
            [--min-cluster-size 15] [--min-samples 5] [--pca-dims 50]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter
from typing import Iterator

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg.types.json import Json


# Common English stopwords + a handful of paper-abstract boilerplate words
# ("paper", "results", "show", etc.) that show up in nearly every cluster
# and add zero signal to a c-TF-IDF label. Kept inline (no nltk) so the
# build script has no extra runtime dependency.
_STOPWORDS: frozenset[str] = frozenset(
    """
a an and or of for to from in on at by with into onto over under between
the this that these those is are was were be been being am do does did
have has had having will would should could may might must can shall
not no nor so as if then than but also too very more most much less few
many some any all every other another such same own its their them they
we us our you your he she it him her his hers
i me my mine myself yourself himself herself itself ourselves themselves
about above after again against among around because before below beside
during except inside outside since through throughout toward towards until
upon via within without
paper papers work works study studies result results show shows shown
showing approach approaches method methods propose proposes proposed
proposing present presents presented presenting use uses used using
new novel framework system systems based perform performs performed
performance experiment experiments experimental evaluation evaluations
also however therefore thus furthermore moreover additionally
""".split()
)

_TOKEN_RE = re.compile(r"[a-z][a-z\-]{1,}")


def _tokenize(text: str) -> list[str]:
    """Lower-cased single-token list, dropping stopwords and very short bits."""
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        tok = tok.strip("-")
        if len(tok) < 3:
            continue
        if tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _ngrams(tokens: list[str]) -> list[str]:
    """Unigrams + bigrams as flat strings, suitable for c-TF-IDF."""
    out: list[str] = list(tokens)
    for a, b in zip(tokens, tokens[1:]):
        out.append(f"{a} {b}")
    return out


def _percentile(values: np.ndarray, pct: float) -> float:
    """5th/95th percentile bbox endpoints. Wraps numpy for type clarity."""
    return float(np.percentile(values, pct))


def _fetch_embeddings_and_coords(
    con: psycopg.Connection, projection: str
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Return ``(paper_ids, embeddings[N,3072], coords[N,2])``.

    Joins ``embedding`` and ``paper_projection_2d`` on paper_id, so a
    paper missing either side is silently skipped (the cluster tree only
    covers papers that show up on this projection anyway).

    Ordered by paper_id so a re-run produces byte-identical input matrices
    — important for HDBSCAN reproducibility downstream.
    """
    register_vector(con)
    print(f"  Fetching embeddings + coords for projection={projection!r}...")
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT pp.paper_id,
                   e.embedding_gemini_embedding_001,
                   pp.x,
                   pp.y
            FROM paper_projection_2d AS pp
            JOIN embedding AS e ON e.paper_id = pp.paper_id
            WHERE pp.projection = %s
              AND e.embedding_gemini_embedding_001 IS NOT NULL
            ORDER BY pp.paper_id
            """,
            [projection],
        )
        rows = cur.fetchall()

    if not rows:
        raise RuntimeError(
            f"No (embedding, projection_2d) rows for projection={projection!r}"
        )

    paper_ids: list[str] = []
    # halfvec values come back as numpy arrays via register_vector, but
    # they're float16 — cast to float32 before PCA for sklearn's BLAS path.
    emb_rows: list[np.ndarray] = []
    xs: list[float] = []
    ys: list[float] = []
    for pid, vec, x, y in rows:
        paper_ids.append(pid)
        # pgvector returns a HalfVector for halfvec columns; .to_numpy()
        # gives us a float16 ndarray. Cast to float32 so sklearn's BLAS
        # path runs on a native-float matrix.
        emb_rows.append(vec.to_numpy().astype(np.float32, copy=False))
        xs.append(float(x))
        ys.append(float(y))

    embeddings = np.vstack(emb_rows)
    coords = np.column_stack(
        [np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)]
    )
    print(
        f"  Loaded {len(paper_ids)} papers; embeddings shape {embeddings.shape}, "
        f"coords shape {coords.shape}"
    )
    return paper_ids, embeddings, coords


def _reduce_pca(embeddings: np.ndarray, n_components: int) -> np.ndarray:
    """Deterministic PCA reduction to ``n_components`` dims."""
    from sklearn.decomposition import PCA

    print(f"  Running PCA -> {n_components} dims on {embeddings.shape[0]} vectors...")
    t0 = time.time()
    pca = PCA(n_components=n_components, random_state=42, svd_solver="randomized")
    reduced = pca.fit_transform(embeddings)
    print(
        f"  PCA done in {time.time() - t0:.1f}s; "
        f"explained_variance_ratio sum={pca.explained_variance_ratio_.sum():.3f}"
    )
    return reduced.astype(np.float32, copy=False)


def _run_hdbscan(reduced: np.ndarray, min_cluster_size: int, min_samples: int):
    """Run HDBSCAN and return the fitted clusterer."""
    import hdbscan

    print(
        f"  Running HDBSCAN min_cluster_size={min_cluster_size} "
        f"min_samples={min_samples} on {reduced.shape[0]} x {reduced.shape[1]}..."
    )
    t0 = time.time()
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        gen_min_span_tree=True,
        # core_dist_n_jobs is the dominant parallel knob; use everything.
        core_dist_n_jobs=-1,
    )
    clusterer.fit(reduced)
    n_noise = int((clusterer.labels_ == -1).sum())
    n_clusters_flat = (
        int(clusterer.labels_.max() + 1) if (clusterer.labels_ >= 0).any() else 0
    )
    print(
        f"  HDBSCAN done in {time.time() - t0:.1f}s; "
        f"flat clusters={n_clusters_flat}, noise points={n_noise}"
    )
    return clusterer


def _walk_condensed_tree(
    clusterer, n_points: int
) -> tuple[
    list[dict],  # rows for atlas_cluster
    dict[int, list[int]],  # cluster_id -> list of original point indices
]:
    """Convert the condensed tree into ``atlas_cluster`` rows + memberships.

    The condensed tree is a structured numpy array with columns
    ``(parent, child, lambda_val, child_size)``.

    - ``parent`` is always a cluster node id (>= n_points)
    - ``child`` is either a leaf point (< n_points) or another cluster
      (>= n_points)
    - ``lambda_val`` is the density level at which ``child`` falls out
      of ``parent`` (which we use as the child's ``lambda_birth``)
    - ``child_size`` is the # points under that child

    For each cluster node, we collect:
    - parent_id (one parent per child by construction)
    - lambda_birth = lambda at which it falls out of its own parent
      (for the implicit root we use 0.0)
    - lambda_death = the maximum lambda at which any *cluster* child
      splits off from it (i.e. the lambda at which it stops being a
      single cluster). For leaf nodes that never split, we use the
      tree's max lambda — they're "alive" all the way down.
    - all descendant point indices for ``atlas_cluster_member``.
    """
    raw = clusterer.condensed_tree_._raw_tree
    # children -> parent map (for cluster nodes only)
    parent_of: dict[int, int] = {}
    # lambda at which a cluster node was born (= lambda_val of the row
    # where the node appears as `child`).
    lambda_of: dict[int, float] = {}
    # lambda at which children leave this cluster — used to compute lambda_death.
    splits_from: dict[int, list[float]] = {}
    # direct child membership map: cluster_id -> list of (child_node, child_size)
    direct_children: dict[int, list[tuple[int, int]]] = {}
    # cluster_id -> list of leaf point indices that fall directly under it
    direct_points: dict[int, list[int]] = {}

    all_cluster_nodes: set[int] = set()
    max_lambda = 0.0

    for parent, child, lambda_val, child_size in raw:
        parent = int(parent)
        child = int(child)
        lam = float(lambda_val)
        max_lambda = max(max_lambda, lam)
        all_cluster_nodes.add(parent)
        if child >= n_points:
            all_cluster_nodes.add(child)
            parent_of[child] = parent
            lambda_of[child] = lam
            splits_from.setdefault(parent, []).append(lam)
            direct_children.setdefault(parent, []).append((child, int(child_size)))
        else:
            direct_points.setdefault(parent, []).append(child)

    if not all_cluster_nodes:
        return [], {}

    # The synthetic root: the smallest cluster id in the condensed tree.
    # It has no parent (parent_of doesn't include it).
    root = min(all_cluster_nodes)
    # For the root, lambda_birth = 0 (alive from the very start).
    lambda_of.setdefault(root, 0.0)

    # All descendants for each cluster (recursive). HDBSCAN's condensed
    # tree is small enough (~few thousand nodes at most) that recursion
    # is fine.
    descendants_cache: dict[int, list[int]] = {}

    def collect(node: int) -> list[int]:
        cached = descendants_cache.get(node)
        if cached is not None:
            return cached
        out: list[int] = []
        out.extend(direct_points.get(node, []))
        for child_node, _ in direct_children.get(node, []):
            out.extend(collect(child_node))
        descendants_cache[node] = out
        return out

    rows: list[dict] = []
    members: dict[int, list[int]] = {}
    for node in sorted(all_cluster_nodes):
        # lambda_death = first lambda at which a child splits off,
        # falling back to max_lambda for leaf clusters that never split.
        # Note: this differs subtly from HDBSCAN's "lambda_death" used
        # internally for stability, but is what we want for tree-slicing
        # ("at lambda L, is this cluster still a single coherent unit?"):
        # below the first child-split, yes; at/after it, no.
        deaths = splits_from.get(node)
        lambda_death = min(deaths) if deaths else float(max_lambda)
        if lambda_death <= lambda_of[node]:
            # Pathological zero-width cluster — push death just above
            # birth so slicing still works.
            lambda_death = lambda_of[node] + 1e-6
        pts = collect(node)
        if not pts:
            continue
        members[node] = pts
        rows.append(
            {
                "cluster_id": node,
                "parent_id": parent_of.get(node),
                "lambda_birth": float(lambda_of[node]),
                "lambda_death": float(lambda_death),
                "paper_count": len(pts),
            }
        )
    return rows, members


def _compute_geometry(
    rows: list[dict],
    members: dict[int, list[int]],
    coords: np.ndarray,
) -> list[dict]:
    """Annotate each cluster row with centroid + 5/95 percentile bbox.

    Mutates ``rows`` in place and returns it for convenience.
    """
    for row in rows:
        cid = row["cluster_id"]
        idxs = members[cid]
        xs = coords[idxs, 0]
        ys = coords[idxs, 1]
        row["centroid_x"] = float(xs.mean())
        row["centroid_y"] = float(ys.mean())
        row["bbox_xmin"] = _percentile(xs, 5)
        row["bbox_ymin"] = _percentile(ys, 5)
        row["bbox_xmax"] = _percentile(xs, 95)
        row["bbox_ymax"] = _percentile(ys, 95)
    return rows


def _iter_titles_and_abstracts(
    con: psycopg.Connection, paper_ids: list[str], batch_size: int = 2000
) -> Iterator[tuple[str, str, str]]:
    """Yield ``(paper_id, title, abstract_prefix)`` for every paper_id.

    Abstract truncated to the first 200 chars per the plan — that's where
    the topical keywords cluster (later sentences pivot into method/
    evaluation specifics that wash out the topic signal).
    """
    with con.cursor() as cur:
        for start in range(0, len(paper_ids), batch_size):
            batch = paper_ids[start : start + batch_size]
            cur.execute(
                "SELECT paper_id, title, abstract FROM paper WHERE paper_id = ANY(%s)",
                [batch],
            )
            for pid, title, abstract in cur.fetchall():
                yield pid, title or "", (abstract or "")[:200]


def _build_term_idf(
    con: psycopg.Connection,
    paper_ids: list[str],
    members: dict[int, list[int]],
) -> tuple[dict[str, int], int]:
    """Per-cluster term sets → global per-term document-frequency.

    Returns ``(term_doc_count, doc_count)``. ``term_doc_count[t]`` is
    the number of clusters in which the term appears at least once;
    ``doc_count`` is the total number of cluster docs scanned.
    """
    # Build paper_id -> token set, streaming.
    print(f"  Fetching titles+abstracts for {len(paper_ids)} papers for term-IDF...")
    t0 = time.time()
    paper_tokens: dict[str, set[str]] = {}
    fetched = 0
    for pid, title, abstract_prefix in _iter_titles_and_abstracts(con, paper_ids):
        toks = _tokenize(f"{title}\n{abstract_prefix}")
        paper_tokens[pid] = set(_ngrams(toks))
        fetched += 1
        if fetched % 50000 == 0:
            print(f"    tokenized {fetched} papers")
    print(f"  Tokenized in {time.time() - t0:.1f}s")

    idx_to_pid = paper_ids  # build_atlas_clusters keeps these aligned
    term_doc_count: Counter[str] = Counter()
    doc_count = 0
    for _cid, point_idxs in members.items():
        cluster_terms: set[str] = set()
        for pi in point_idxs:
            pid = idx_to_pid[pi]
            cluster_terms |= paper_tokens.get(pid, set())
        for t in cluster_terms:
            term_doc_count[t] += 1
        doc_count += 1
    return dict(term_doc_count), doc_count


def _persist(
    con: psycopg.Connection,
    projection: str,
    rows: list[dict],
    members: dict[int, list[int]],
    paper_ids: list[str],
    term_doc_count: dict[str, int],
    doc_count: int,
) -> None:
    """Replace all atlas_cluster* rows for ``projection`` in one transaction."""
    print(
        f"  Persisting {len(rows)} clusters, {sum(len(v) for v in members.values())} memberships..."
    )
    t0 = time.time()
    with con.cursor() as cur:
        # Wipe prior runs for this projection. ON DELETE CASCADE on
        # atlas_cluster_member and atlas_cluster_label takes care of the
        # dependent rows.
        cur.execute(
            "DELETE FROM atlas_cluster_label WHERE projection = %s", [projection]
        )
        cur.execute(
            "DELETE FROM atlas_cluster_member WHERE projection = %s", [projection]
        )
        cur.execute("DELETE FROM atlas_cluster WHERE projection = %s", [projection])
        cur.execute(
            "DELETE FROM atlas_cluster_term_idf WHERE projection = %s", [projection]
        )
        cur.execute(
            "DELETE FROM atlas_cluster_term_stats WHERE projection = %s",
            [projection],
        )

        # Bulk insert atlas_cluster.
        cur.executemany(
            """
            INSERT INTO atlas_cluster (
              projection, cluster_id, parent_id, lambda_birth, lambda_death,
              paper_count, centroid_x, centroid_y,
              bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    projection,
                    r["cluster_id"],
                    r["parent_id"],
                    r["lambda_birth"],
                    r["lambda_death"],
                    r["paper_count"],
                    r["centroid_x"],
                    r["centroid_y"],
                    r["bbox_xmin"],
                    r["bbox_ymin"],
                    r["bbox_xmax"],
                    r["bbox_ymax"],
                )
                for r in rows
            ],
        )

        # Bulk insert atlas_cluster_member with copy_expert for speed.
        # 524k papers × ~depth-of-tree memberships per paper can be a
        # few million rows; copy is ~10× faster than executemany.
        member_tuples: list[tuple[str, int, str]] = []
        for cid, pts in members.items():
            for pi in pts:
                member_tuples.append((projection, cid, paper_ids[pi]))
        with cur.copy(
            "COPY atlas_cluster_member (projection, cluster_id, paper_id) FROM STDIN"
        ) as cp:
            for t in member_tuples:
                cp.write_row(t)

        # Persist the global term-IDF sidecar.
        if term_doc_count:
            with cur.copy(
                "COPY atlas_cluster_term_idf (projection, term, cluster_count) FROM STDIN"
            ) as cp:
                for term, cnt in term_doc_count.items():
                    cp.write_row((projection, term, cnt))
        cur.execute(
            """
            INSERT INTO atlas_cluster_term_stats (projection, doc_count)
            VALUES (%s, %s)
            """,
            [projection, doc_count],
        )

    con.commit()
    # ``Json`` is imported just to keep psycopg happy in case we ever
    # want to round-trip a jsonb keyword list from this script.
    _ = Json
    print(f"  Persist done in {time.time() - t0:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", required=True)
    parser.add_argument("--min-cluster-size", type=int, default=15)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--pca-dims", type=int, default=50)
    args = parser.parse_args()

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    overall_t0 = time.time()
    with psycopg.connect(database_url) as con:
        paper_ids, embeddings, coords = _fetch_embeddings_and_coords(
            con, args.projection
        )
        reduced = _reduce_pca(embeddings, args.pca_dims)
        # Free the 3072-d copy — 524k × 3072 × 4B = ~6 GiB.
        del embeddings

        clusterer = _run_hdbscan(reduced, args.min_cluster_size, args.min_samples)
        # Free 50-d copy too once HDBSCAN is done.
        del reduced

        rows, members = _walk_condensed_tree(clusterer, n_points=len(paper_ids))
        print(f"  Condensed tree size: {len(rows)} cluster nodes")
        rows = _compute_geometry(rows, members, coords)

        term_doc_count, doc_count = _build_term_idf(con, paper_ids, members)
        print(
            f"  Term-IDF: {len(term_doc_count)} unique terms, {doc_count} cluster docs"
        )

        _persist(
            con,
            args.projection,
            rows,
            members,
            paper_ids,
            term_doc_count,
            doc_count,
        )

    print(f"All done in {time.time() - overall_t0:.1f}s")


if __name__ == "__main__":
    main()
