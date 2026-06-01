# Plan: fractal cluster labels on the paper atlas

## Motivation

The atlas page shows 524k paper positions in 2D but has no semantic labels
telling the user *what* each region is. As they zoom in, finer regions
should surface finer-grained labels — like a city map showing country →
state → city → neighbourhood.

Constraints:
- **Fractal / continuous**: labels must be available at any zoom level the
  user lands on, not just 3 pre-baked tiers.
- **Lazy**: don't pre-compute every label at every level. Label only the
  regions the user actually visits, cache forever.
- **Free**: no LLM in the hot path. Keyword-based labels via class TF-IDF.
- **Honest geography**: labels follow real density, not an artificial grid
  imposed on the 2D coords.

## Design summary

| Component | Approach |
|---|---|
| Cluster shape | HDBSCAN's condensed tree, computed once per projection |
| Cluster granularity | Pick any lambda value from the tree → get clusters at that density |
| Labels | Class TF-IDF over abstracts, top n-grams |
| Generation | Lazy on first viewport request, cached in Postgres forever |
| Frontend rendering | HTML overlay, label position = cluster centroid, opacity & font size scale with paper_count |

The condensed tree is the "fractal" part: HDBSCAN's `condensed_tree_` has a
continuous lambda axis. Slicing at any lambda yields a complete cluster
partition. The user's zoom level maps to a target cluster count, and we
pick the lambda that produces roughly that many clusters in the viewport.

## Pipeline overview

```
            (one-time, per projection)               (on every viewport request)
PaCMAP coords ─┐                              ┌─────────────────────────────┐
               │                              │                             │
PCA-50 dims ───┼──> HDBSCAN.fit() ──> tree    │  /api/atlas/labels         │
               │       │                      │   ?projection=X            │
papers, ids ───┘       └─> persist tree:      │   &viewport=xmin,ymin,...  │
                           atlas_cluster      │   &target_count=30         │
                           atlas_cluster_member│                            │
                                              │  1. slice tree to find     │
                                              │     ~target_count clusters │
                                              │     intersecting viewport  │
                                              │  2. for each, GET label    │
                                              │     from atlas_cluster_label│
                                              │     — if missing, compute  │
                                              │     c-TF-IDF and insert    │
                                              │  3. return labels + bboxes │
                                              └─────────────────────────────┘
```

## Schema

```sql
-- Stores the full HDBSCAN tree once per projection.
-- The tree is the fractal: every cluster that ever could be returned at
-- any zoom level is here.
CREATE TABLE atlas_cluster (
    projection   varchar  NOT NULL,
    cluster_id   int      NOT NULL,          -- node id in condensed tree
    parent_id    int      NULL,              -- NULL only for the root
    lambda_birth real     NOT NULL,          -- density level at which this cluster appears
    lambda_death real     NOT NULL,          -- density level at which it splits/dissolves
    paper_count  int      NOT NULL,
    centroid_x   real     NOT NULL,          -- in PaCMAP-2D space
    centroid_y   real     NOT NULL,
    bbox_xmin    real     NOT NULL,          -- 5th/95th percentile of member coords,
    bbox_ymin    real     NOT NULL,          -- not min/max (resilient to outliers)
    bbox_xmax    real     NOT NULL,
    bbox_ymax    real     NOT NULL,
    PRIMARY KEY (projection, cluster_id)
);
CREATE INDEX atlas_cluster_proj_bbox_idx
    ON atlas_cluster (projection, bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax);
CREATE INDEX atlas_cluster_proj_lambda_idx
    ON atlas_cluster (projection, lambda_birth);

-- Cluster membership (which papers are in which cluster).
-- Lots of rows but small. Needed for label generation and for FE
-- "highlight this cluster's papers" interactions later.
CREATE TABLE atlas_cluster_member (
    projection  varchar  NOT NULL,
    cluster_id  int      NOT NULL,
    paper_id    varchar  NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
    PRIMARY KEY (projection, cluster_id, paper_id)
);
CREATE INDEX atlas_cluster_member_paper_idx
    ON atlas_cluster_member (projection, paper_id);

-- Labels are stored lazily — one row appears the first time a cluster
-- is viewed at any zoom level. Forever cached.
CREATE TABLE atlas_cluster_label (
    projection   varchar     NOT NULL,
    cluster_id   int         NOT NULL,
    label        varchar     NOT NULL,           -- "type theory · linear · dependent"
    keywords     jsonb       NOT NULL,           -- ["type theory", "linear", "dependent", ...]
    method       varchar     NOT NULL,           -- "c_tfidf_v1" — future: "llm_polish_v1"
    generated_at timestamp   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (projection, cluster_id),
    FOREIGN KEY (projection, cluster_id)
        REFERENCES atlas_cluster (projection, cluster_id) ON DELETE CASCADE
);
```

Notes on the cluster tree:
- **`lambda_birth` / `lambda_death`** are HDBSCAN's persistence values. A
  cluster is "alive" at any lambda in `[birth, death)`. Slicing the tree
  at lambda L means: pick every cluster where `birth <= L < death`.
- **`parent_id`** lets the FE later add "zoom into this cluster" by
  walking children, or "what's the parent of this cluster" for breadcrumbs.

## API

```
GET /api/atlas/labels
    ?projection=pacmap_v1
    &viewport=xmin,ymin,xmax,ymax
    &target_count=6                     (FE asks for ~N labels, default 6)
```

`target_count` is user-configurable from the atlas control panel
(see Frontend integration below). Default is **6**. Backend should
clamp to a sane range (say 1–50) — beyond ~50 the labels start
overlapping unreadably even at high zoom.

Behaviour:
1. Find the lambda value where slicing the tree gives ≈ `target_count`
   clusters whose bbox overlaps the viewport. Binary search on the
   sorted distinct `lambda_birth` values for this projection.
2. Return those clusters (cluster_id, centroid, bbox, paper_count).
3. For each: fetch its row from `atlas_cluster_label`. Missing rows
   trigger a c-TF-IDF computation, get inserted, and are returned.
4. Cap latency: if more than ~K (say 20) labels need fresh generation,
   return the cached ones plus a `pending: [cluster_id, ...]` list.
   FE re-fetches in a follow-up call with `&include_pending=true`.

Response shape:

```json
{
  "labels": [
    {
      "cluster_id": 4271,
      "centroid": [3.2, -1.7],
      "bbox": [2.1, -2.4, 4.5, -1.0],
      "paper_count": 487,
      "label": "type theory · dependent · inference",
      "keywords": ["type theory", "dependent", "inference"]
    }
  ],
  "pending": [4279, 4283]
}
```

## Cluster computation (one-shot per projection)

Script `scripts/build_atlas_clusters.py`:

1. Fetch the PCA-50 embeddings used for the PaCMAP run (re-run that PCA
   on the embeddings table — it's deterministic given `random_state=42`,
   so we get exactly the same 50-dim representation).
2. Run `hdbscan.HDBSCAN(min_cluster_size=15, min_samples=5, gen_min_span_tree=True)`
   on the 50-dim representation. **Not** on the 2D PaCMAP coords —
   those are lossy and would group unrelated things that happened to
   project close.
3. Extract the **condensed tree** (`clusterer.condensed_tree_._raw_tree`).
   Each row is `(parent, child, lambda_val, child_size)`. Walk it to
   produce the `atlas_cluster` rows with lambda_birth / lambda_death
   per node.
4. For each cluster, compute centroid + 5/95 percentile bbox from its
   members' 2D coords (queried from `paper_projection_2d`).
5. Populate `atlas_cluster` and `atlas_cluster_member` in one transaction.

Cost: HDBSCAN on 524k × 50 dims is ~5-15 minutes CPU. One-shot.

## Label computation (lazy, on cache miss)

Function `compute_cluster_label(projection, cluster_id)`:

1. Look up all `paper_id`s in `atlas_cluster_member`.
2. Fetch `(title, abstract)` rows from `paper`.
3. Concatenate into one "document" per cluster.
4. **c-TF-IDF**: tokenize (basic lowercase + stopword removal + bigrams),
   compute term frequencies in the cluster, divide by the term's
   frequency across all clusters (the "class-based IDF"). Sort terms
   desc by c-TF-IDF score.
5. Filter terms: drop tokens shorter than 3 chars, drop pure-numeric,
   drop terms that appear in > 95% of clusters (uninformative).
6. Take top 3 distinct lemmas (so we don't get "type", "types", "typed"
   all at once). Join with " · ".
7. Insert into `atlas_cluster_label` with `method = 'c_tfidf_v1'`.

Time per cluster: 50-200ms depending on member count. Most labels
should be served on first request without a noticeable delay.

The global "term frequency across all clusters" is computed once at
HDBSCAN-build time and cached as a sidecar table or in-memory pickle.
Don't recompute on every label miss.

## Frontend integration

(Atlas page on `paper-atlas` branch.)

### Control panel

Introduce a small control panel UI element on the atlas page —
position TBD, but a collapsible panel pinned to a corner is a
reasonable starting point. This is where the user adjusts
visualization parameters. It anchors future controls (label
specificity, max paper age, etc.); for v1 it holds **one** control:

- **Label density** — slider or number input controlling `target_count`.
  Default **6**. Range 1–50. The frontend persists this value in
  `localStorage` so it survives reloads. Changes refetch labels
  immediately.

This makes the labels-per-screen tunable per user preference. The
"if labels collide, zoom in" rule still holds, but users who like a
denser map can bump it up; users who want a clean overview can dial
it down.

### Label rendering

1. On viewport change (debounced ~200ms), compute current viewport
   bbox from regl-scatterplot's camera, fetch `/api/atlas/labels`
   with the current `target_count` from the control panel.
2. Render labels as absolutely-positioned HTML elements inside the
   scatter container. Position uses the same world-to-screen transform
   the scatter uses (expose `scatter.getCamera()`).
3. Font size and opacity scale with `paper_count`:
   - `fontSize = clamp(10, 12 + 2 * log10(paper_count), 28)`
   - `opacity = clamp(0.5, log10(paper_count) / 4, 1.0)`
4. **No collision detection.** If labels overlap, the user zooms in.
   This keeps the label-fetch loop simple and avoids the noisy
   "label disappears as I pan" behaviour collision detection causes.
   The target-count control (below) is the user's lever for tuning
   label density to their preference.
5. **Click on a label** → zoom the scatter camera so the cluster's
   bbox fills the viewport, then re-fetch labels (which now returns
   the children of that cluster).
6. **Optimisation**: keep a label cache in the frontend keyed by
   cluster_id. As the user pans, labels with stable cluster_ids
   smoothly fade rather than disappear/reappear.

## Phasing

Each phase ships independently — every phase is a useful state to land
in even if no further work happens.

### Phase 1 — backend foundations

- New tables (`atlas_cluster`, `atlas_cluster_member`,
  `atlas_cluster_label`).
- `scripts/build_atlas_clusters.py` runs HDBSCAN, populates tree tables.
- Run it for both existing projections (`pacmap_pl_v1`, `pacmap_v1`).
- No API endpoint yet, no FE.

### Phase 2 — lazy label generation

- c-TF-IDF computation + global term-freq sidecar.
- `compute_cluster_label()` function.
- `GET /api/atlas/labels` endpoint, fully working server-side.
- Verify via curl: hand-pick a cluster, confirm label is sensible.

### Phase 3 — frontend labels + control panel

- Control panel scaffolding on the atlas page (collapsible corner-pinned
  component, ready to host future controls).
- Label-density control inside it (default `target_count=6`, persisted
  to localStorage).
- HTML label overlay on the atlas page.
- World-to-screen transform synced with regl-scatterplot.
- Font/opacity scaling.

### Phase 4 — interaction

- Click label → zoom into cluster.
- Breadcrumb trail using `parent_id`.
- Hover label → highlight cluster's papers on the scatter.

### Phase 5 (optional) — LLM polish

- Post-process c-TF-IDF top-3 with an LLM call to produce a clean
  human phrase. Cache as a separate `method='llm_polish_v1'` row so
  c-TF-IDF labels remain the fallback if the LLM call fails.

## Risks and open questions

- **HDBSCAN parameter choice.** `min_cluster_size=15` is a guess. Too
  small → too many tiny clusters at deep zoom. Too large → not enough
  granularity. Need to eyeball the tree size and adjust before
  committing to it.
- **Label quality at very-small clusters.** A cluster of 15 papers may
  not have enough distinctive vocabulary for c-TF-IDF. Could mitigate
  by inheriting the parent's label and prepending the most-discriminating
  child-specific keyword.
- **Tree slicing latency.** Naive: scan all clusters in the projection.
  At 524k papers / `min_cluster_size=15`, the tree has ~30k-50k nodes.
  Scanning all of them per request is fine in-memory but ugly in SQL.
  May need to keep the tree in process memory in the Flask app
  (load on first request, cache forever).
- **Lambda → target-count mapping.** Binary search works, but at the
  *root* of the tree (target_count=1) there's only one cluster and at
  the *leaves* (target_count=30k) the labels are useless. Need
  sensible defaults and clamps.
- **Outlier/noise points.** HDBSCAN labels some points as noise
  (cluster -1). These won't appear in any cluster, so their region
  on the map has no label. Acceptable — noise points are by definition
  not part of any topic.
- **Re-running with a new projection.** Cluster tree is per-projection,
  so swapping `pacmap_v1` for a future `pacmap_v2` means re-running
  HDBSCAN. Labels don't carry over (different clusters). Acceptable
  cost given a new projection is a rare event.
- **Re-running with new papers ingested.** If 1000 new papers come in
  via daily sync, their embeddings could be:
  - Assigned to existing clusters (HDBSCAN's `approximate_predict`),
    and folded in without retraining. Cheap, slightly degrades over
    time.
  - Trigger a re-cluster periodically (e.g. weekly). Expensive but
    keeps the tree accurate.
  Defer to a follow-up.

## What this *doesn't* cover

- LLM-generated labels in the hot path (deliberately ruled out).
- Multi-resolution tile pre-rendering (the labels themselves are
  lightweight HTML, no need).
- Time-varying labels (e.g. "AI in 2015" vs "AI in 2024"). Could
  be done by stratifying clusters by date later.
- Cross-projection consistency (labels on `pacmap_pl_v1` are
  independent of labels on `pacmap_v1`).
