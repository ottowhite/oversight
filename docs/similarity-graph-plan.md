# Plan: semantic similarity graph UI

## Motivation

Search is good for "find papers about X." It's bad for "I just read this paper —
what else is in this neighborhood?" A graph view where each node is a paper and
edges encode abstract-embedding similarity lets the user navigate by adjacency
rather than by query, which is the right interface for browsing a research
neighborhood.

## Approach

**On-demand neighbor expansion.** Start with one seed paper (chosen from a
search result). Click any node → fetch its similar papers from the backend
→ add them as connected nodes. Edges are weighted by cosine similarity.

Pre-computing the full graph is unnecessary at our scale (see Performance
below). On-demand keeps the architecture simple, stays fresh as we ingest, and
costs ~6ms p50 per click.

### Modes

The user picks the neighbor-selection mode in the UI. Three modes are
exposed, but only two require backend support — threshold is just a
client-side filter on top of top-k:

| Mode | What it returns | Where the work happens |
|---|---|---|
| **top-k** | The k nearest neighbors of the clicked node | Backend (HNSW kNN) |
| **threshold** | Neighbors with cosine similarity ≥ T | Client (filter the cached top-N) |
| **mutual-kNN** | Edges where A is in B's top-k *and* B is in A's top-k | Backend (needs reverse kNN) |

The threshold mode reuses the top-N cache. If the user ever has more than N
papers above their threshold, the graph would be unreadable anyway —
truncation at N is the right default behavior, not a limitation. Set
**N = 20** as the over-fetch ceiling: small enough to keep any single
node's expansion legible, comfortably above any reasonable top-k slider
range.

Defaults: top-k with k=15.

#### Statistical caveats the UI must surface

Embedding cosine values are not calibrated probabilities. In high dimensions,
random pairs of academic CS papers cluster around some background similarity
(typically 0.3–0.6), not around 0. Hubness means a few "hub" papers appear as
nearest neighbors to disproportionately many others; papers in sparse regions
have no above-threshold neighbors at all.

Implications for each mode:
- **top-k** always returns exactly k neighbors, even when the kth is barely
  above background. The UI should encode similarity as edge opacity so the
  user can see a "weak tail."
- **mutual-kNN** returns variable degree per node (0 to k), which is the
  honest answer but can produce isolated nodes. Show the degree somewhere.
- **threshold** is the most fragile: a global T that works for hub papers
  may return zero neighbors for sparse-region papers. Mitigate by showing a
  per-corpus calibration in the slider — e.g., a small histogram of pairwise
  similarities sampled from the DB, with the current T marked. The user then
  sees "you're at the 99.5th percentile" rather than picking a raw cosine
  number with no anchor.

## Performance (measured, not estimated)

Benchmark on the live DB (472K embedded papers, halfvec(3072), HNSW m=32
ef_construction=400):

```
Full round-trip per click (seed-fetch + kNN):
   k    ef_search   p50    p95    p99    max   (ms)
   10   40          6.0    8.1    9.4    9.9
   20   80          8.7    11.5   13.8   14.0
   50   200         14.9   22.1   28.1   28.2
```

**Critical SQL note:** the kNN must be a two-step query — first SELECT the seed
paper's embedding as a literal, then SELECT the kNN with that literal as a
parameter. A self-join (`FROM embedding e1, embedding e2 ORDER BY e2.emb <=>
e1.emb`) prevents the planner from using the HNSW index and falls back to a
brute-force scan (~5400ms p50). We hit this in the benchmark; do not repeat it.

### Per-mode efficiency

- **top-k** uses the HNSW index directly: `ORDER BY emb <=> $seed LIMIT k`.
  The benchmark numbers above are this case.
- **threshold** is a client-side filter on the cached top-N response — no
  backend involvement. Slider drags = pure React re-renders.
- **mutual-kNN** is two top-k queries in one round-trip via a CTE: get A's
  top-k, then for each candidate B, do a top-k against B's embedding and
  check if A is in it. SQL pattern:

  ```sql
  WITH seed_neighbors AS (
    SELECT paper_id, embedding_gemini_embedding_001 AS emb
    FROM embedding
    WHERE embedding_gemini_embedding_001 IS NOT NULL
    ORDER BY embedding_gemini_embedding_001 <=> $1::halfvec
    LIMIT $2  -- k+1 to drop self
  )
  SELECT sn.paper_id, ...
  FROM seed_neighbors sn
  WHERE EXISTS (
    SELECT 1 FROM (
      SELECT paper_id FROM embedding
      WHERE embedding_gemini_embedding_001 IS NOT NULL
      ORDER BY embedding_gemini_embedding_001 <=> sn.emb
      LIMIT $2
    ) rev WHERE rev.paper_id = $seed_id
  )
  ```

  Expected ~k × 6ms = ~90ms for k=15. Acceptable for a click but **too slow
  for live slider drags** — see slider strategy below.

### Cache strategy: over-fetch once, derive everything

On first click of a node, fetch top-N (N=20). All non-mutual modes derive
from that cache without further round-trips:

1. Fetch `/api/papers/<id>/neighbors?k=20` once, cache the result.
2. As the user adjusts the slider:
   - top-k → `cached.slice(0, k)`
   - threshold → `cached.filter(s => s.similarity ≥ T)`
3. Mutual-kNN is a separate fetch (`?mutual=true`) that also caches; mode
   flip triggers it once, slider drags within mutual-kNN slice from that
   cache.

Top-k and threshold drags are pure React re-renders, no network. Mutual-kNN
drags also hit zero network once the initial mutual fetch is cached.

## Backend

One endpoint, two query params:

```
GET /api/papers/<id>/neighbors?k=20&mutual=false
```

- `k` — number of neighbors to return (default 20; the over-fetch ceiling).
- `mutual` — when true, restrict to mutual-kNN edges; otherwise plain top-k.

Response:
```json
{
  "seed": { "paper_id": "...", "title": "...", "authors": [...] },
  "neighbors": [
    { "paper_id": "...", "title": "...", "authors": [...], "similarity": 0.78 }
  ]
}
```

Implementation:
- `PaperDatabase.find_neighbors(paper_id, k, mutual, ef_search)` dispatches
  to one of two SQL templates (the top-k query above, or the mutual-kNN CTE).
- `PaperRepository.get_neighbors(...)` mirrors and handles embedding-model
  selection.
- Wire into `flask_app.py` with input validation (`k ≤ 50` as a safety cap,
  `mutual` parsed as bool).

Threshold is not a backend concept — it's a client-side filter on
`neighbors[].similarity`. This keeps the backend surface area minimal and
the threshold slider instant.

A separate small endpoint anchors the threshold slider in corpus
percentiles:

```
GET /api/embeddings/similarity_distribution
```

Returns precomputed percentile breakpoints (50th, 90th, 95th, 99th, 99.5th,
99.9th) sampled from ~10K random embedding pairs. Cached server-side,
refreshed weekly or on big ingests. Without this anchor, the user is
sliding a raw cosine number with no reference for "what's a meaningful
threshold for this corpus."

## Frontend

New page `frontend/pages/graph.tsx`. Library: `react-force-graph-2d`
(Canvas-based, handles thousands of nodes, built-in zoom/pan/click).

### State

```ts
type Mode = "topk" | "threshold" | "mutual_knn";

type Neighbor = { paper_id: string; similarity: number };

type NodeCache = {
  paper_id: string;
  topN: Neighbor[];           // fetched once with ?k=20
  mutualN?: Neighbor[];       // fetched on first switch into mutual_knn mode
};

type GraphState = {
  nodes: Paper[];
  edges: { source: string; target: string; similarity: number }[];
  mode: Mode;
  k: number;          // for topk / mutual_knn
  threshold: number;  // for threshold
  cache: Record<string, NodeCache>;
};
```

### Controls panel

A floating panel (top-right) with:
- Mode tabs: `top-k` / `threshold` / `mutual-kNN`.
- A single slider whose meaning depends on the active mode:
  - `top-k`: integer k, range 1–20 (capped by the over-fetch ceiling).
  - `threshold`: float T, range [min, max] of the corpus distribution
    (fetched from `/api/embeddings/similarity_distribution`). Show a small
    histogram behind the slider with the current percentile labelled
    ("99.5th"). This is the anchor that makes thresholds usable.
  - `mutual-kNN`: integer k_max, range 1–20 (also capped by the ceiling).
- Mode-toggle resets to sensible default (k=15, T=corpus 99th percentile,
  k_max=15) but keeps the cached fetches.

### Live slider behavior

The slider drives a re-derivation of edges from cache. The only network
calls are:

- First click of a new node → fetch top-20.
- First switch into mutual-kNN mode for a node already in the graph →
  fetch mutual-kNN edges.

Both are cached forever (per session). All slider drags within an
already-cached mode are pure React re-renders. No debouncing needed for
the cached cases.

The force-graph library accepts incremental node/edge updates without
restarting the simulation, so re-derivation feels like edges fading
in/out rather than a re-layout.

### Visual encoding

- Edge similarity → opacity and length (force-graph spring strength = sim).
- Node degree → size. Helps the user spot hubs.
- Hover → tooltip with title + authors + similarity to seed.
- In `mutual-kNN` mode, edges that are *not* mutual are hidden; in `top-k`
  mode they're shown faintly with a dashed stroke (cheap visual hint that
  the relationship is one-way).

### Seed flow

Link from each search result on `index.tsx` to `/graph?seed=<paper_id>`.
The graph page fetches `/api/papers/<id>` for the seed and renders a
single-node graph, ready for expansion.

## Subagent decomposition

The API contract (endpoint shapes, response JSON) is the critical interface.
Pin it first, then backend and frontend can run in parallel.

### Phase 0 (sequential, blocking) — define API contract

Single agent. Output: a short markdown spec listing endpoint paths, query
params, request/response JSON shapes. Both downstream agents consume this.

Estimated time: 15 min.

### Phase 1 (parallel) — three independent workstreams

Three agents, no shared files.

**Agent A — backend neighbors endpoint**
- Add `find_neighbors(paper_id, k, mutual, ef_search)` to `PaperDatabase.py`
  with two SQL templates (top-k, mutual-kNN-CTE). Both use the two-step
  seed-fetch + parameterized kNN pattern from the benchmark.
- Add `get_neighbors` to `PaperRepository.py`.
- Wire `GET /api/papers/<id>/neighbors?k=&mutual=` into `flask_app.py` with
  input validation (`k ≤ 50`, `mutual` parsed as bool).
- Smoke test both modes against the dev DB and assert latency budgets:
  topk ≤ 30ms, mutual ≤ 200ms (p95 over 50 trials).
- Files touched: `src/oversight/PaperDatabase.py`,
  `src/oversight/PaperRepository.py`, `src/oversight/flask_app.py`,
  one test file.

**Agent B — backend distribution endpoint + corpus calibration**
- Add `sample_pairwise_similarities(n)` to `PaperDatabase.py` — pulls n
  random embedding pairs, computes cosine, returns the array.
- Wire `GET /api/embeddings/similarity_distribution` with server-side
  caching (recompute only on demand or weekly).
- Compute and report the percentile breakpoints (50th, 90th, 95th, 99th,
  99.5th, 99.9th) so the frontend doesn't need to do it.
- Files touched: same backend files; no overlap with Agent A's *functions*
  (separate methods/routes), but they edit the same files.

  ⚠ Agent A and Agent B both edit `flask_app.py` and `PaperDatabase.py`. To
  avoid merge conflicts, either (a) run them sequentially, or (b) tell each
  agent to append a clearly-scoped section and rely on git's three-way merge.
  Recommend (a) — Agent B is small (~30 min), so do it after Agent A.

**Agent C — frontend graph page with mode controls**
- `npm install react-force-graph-2d`.
- Create `frontend/pages/graph.tsx` with the full state shape, controls
  panel, slider, force-graph component. Mock all API responses inline
  (return canned `cachedNeighbors` arrays) so it renders without the
  backend.
- Implement the cache + client-side re-derivation logic for top-k and
  threshold modes against the mocked data — this is the main interaction
  loop and the hardest part to get right; must be done with mocks before
  integration.
- Apply Tailwind/DaisyUI dark theme to match `index.tsx`.
- Files touched: `frontend/pages/graph.tsx`, `frontend/package.json`.

Estimated wall time with Agent A + Agent C in parallel: ~60 min. Agent B
follows Agent A: ~30 min.

### Phase 2 (sequential, depends on Phase 1) — integration

Single agent.
- Replace mocked fetches in `graph.tsx` with real calls. Confirm cache layer
  works against the real backend (cache key = paper_id, value = the top-20
  payload).
- Wire the threshold slider to fetch `/api/embeddings/similarity_distribution`
  on mount and render the histogram behind the slider.
- Add "graph" link on each search result in `index.tsx` →
  `/graph?seed=<paper_id>`.
- Manual smoke test in `make dev`: search → graph, drag the slider in each
  mode and verify the cache prevents re-fetches in topk/threshold modes
  (network tab should be quiet during drags), verify mutual-kNN edges look
  reciprocal.
- Files touched: `frontend/pages/graph.tsx`, `frontend/pages/index.tsx`.

Estimated time: 45 min.

### Phase 3 (optional, parallel with Phase 2) — visual polish

Independent of integration; operates on the rendered graph component.

- Edge opacity/length encoding by similarity.
- Node hover tooltip with title + authors + similarity.
- Dashed stroke for non-mutual edges in top-k mode.
- Keyboard shortcuts: `r` reset, `f` fit-to-view, `1`/`2`/`3` switch mode.
- Files touched: `frontend/pages/graph.tsx` only.

### Dependency summary

```
Phase 0 (API contract)
   │
   ├──> Phase 1A (backend neighbors)  ──> Phase 1B (backend distribution) ──┐
   │                                                                        │
   └──> Phase 1C (frontend, mocked)  ───────────────────────────────────────┤
                                                                            │
                                              Phase 2 (integration)  <──────┤
                                                    │
                                                    └──> Phase 3 (polish)
```

True parallelism: **Phase 1A and 1C** (different files, different languages,
nothing shared). **Phase 1B is sequential after 1A** because both edit the
same backend files; conflict-avoidance is more valuable than the ~30 min of
parallelism gained.

The cache + client-side re-derivation logic in Phase 1C is the main risk —
get the mock data shape exactly matching the API contract from Phase 0,
otherwise Phase 2 integration becomes a rewrite instead of a swap.

## Out of scope (for now)

- Pre-computed `paper_neighbors` table. Revisit only if we add a "global map"
  view (e.g., UMAP projection of all papers).
- Per-cluster topic labels.
- Persistence of explored graphs across sessions.
- Filtering edges by date / venue / author overlap. Easy to add later as query
  params on the neighbors endpoint.
