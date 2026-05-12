-- Fractal cluster tree for the /atlas page's lazy-label system.
--
-- The condensed HDBSCAN tree is materialized once per projection; every
-- cluster the FE could possibly request at any zoom level is a row in
-- ``atlas_cluster``. Slicing the tree at a given ``lambda`` (= picking
-- nodes where ``lambda_birth <= L < lambda_death``) yields a complete
-- partition at that density. The "fractal" effect is just continuous L.
--
-- ``atlas_cluster_member`` is the per-paper inverse — needed for label
-- generation (c-TF-IDF over cluster's titles+abstracts) and for FE
-- "highlight this cluster's papers" interactions.
--
-- ``atlas_cluster_label`` is the cache. Lazy: rows appear the first
-- time a cluster is rendered. Forever-valid because clusters are
-- immutable for a given projection.

CREATE TABLE IF NOT EXISTS atlas_cluster (
    projection   varchar  NOT NULL,
    cluster_id   int      NOT NULL,          -- node id in the condensed tree
    parent_id    int      NULL,              -- NULL only for the root pseudo-node
    lambda_birth real     NOT NULL,          -- density at which this cluster appears
    lambda_death real     NOT NULL,          -- density at which it dissolves / splits
    paper_count  int      NOT NULL,
    centroid_x   real     NOT NULL,          -- 2D PaCMAP centroid
    centroid_y   real     NOT NULL,
    bbox_xmin    real     NOT NULL,          -- 5th/95th percentile of member coords,
    bbox_ymin    real     NOT NULL,          -- not min/max (resilient to outliers)
    bbox_xmax    real     NOT NULL,
    bbox_ymax    real     NOT NULL,
    PRIMARY KEY (projection, cluster_id)
);

CREATE INDEX IF NOT EXISTS atlas_cluster_proj_bbox_idx
    ON atlas_cluster (projection, bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax);
CREATE INDEX IF NOT EXISTS atlas_cluster_proj_lambda_idx
    ON atlas_cluster (projection, lambda_birth);

-- Cluster membership. PK on (projection, cluster_id, paper_id) supports
-- "all members of this cluster" lookups; the auxiliary index on
-- (projection, paper_id) lets the FE answer "which cluster(s) is paper
-- X in?" without scanning the full tree.
CREATE TABLE IF NOT EXISTS atlas_cluster_member (
    projection  varchar  NOT NULL,
    cluster_id  int      NOT NULL,
    paper_id    varchar  NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    PRIMARY KEY (projection, cluster_id, paper_id)
);

CREATE INDEX IF NOT EXISTS atlas_cluster_member_paper_idx
    ON atlas_cluster_member (projection, paper_id);

-- Lazy label cache. One row per cluster the FE has ever requested.
-- ``method`` tags which generator produced this row so a future LLM
-- polish pass (`c_tfidf_v1` → `llm_polish_v1`) can be stored alongside
-- the cheap c-TF-IDF fallback for the same cluster_id.
CREATE TABLE IF NOT EXISTS atlas_cluster_label (
    projection   varchar     NOT NULL,
    cluster_id   int         NOT NULL,
    label        varchar     NOT NULL,           -- "type theory · linear · dependent"
    keywords     jsonb       NOT NULL,           -- ["type theory", "linear", "dependent"]
    method       varchar     NOT NULL,           -- "c_tfidf_v1"
    generated_at timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (projection, cluster_id),
    FOREIGN KEY (projection, cluster_id)
        REFERENCES atlas_cluster (projection, cluster_id) ON DELETE CASCADE
);

-- Sidecar for c-TF-IDF: global per-term document frequency (where each
-- cluster is one "document"). Computed once at HDBSCAN-build time, used
-- on every label-cache miss to compute the IDF half of c-TF-IDF.
-- ``doc_count`` is the total number of clusters considered so the IDF
-- math doesn't need an extra round-trip.
CREATE TABLE IF NOT EXISTS atlas_cluster_term_idf (
    projection      varchar  NOT NULL,
    term            varchar  NOT NULL,
    cluster_count   int      NOT NULL,   -- # clusters containing this term
    PRIMARY KEY (projection, term)
);

CREATE TABLE IF NOT EXISTS atlas_cluster_term_stats (
    projection      varchar  NOT NULL PRIMARY KEY,
    doc_count       int      NOT NULL,   -- total cluster docs considered
    built_at        timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
