# Plan: stream atlas points instead of bulk-and-block

## Motivation

Today the `/atlas` page does a one-shot fetch of every point in the
projection, then renders. At the current 524k-point `pacmap_v1` projection
that costs ~8–11 s of "Loading atlas…" with nothing on screen. Measured
breakdown:

```
DB query (524k rows JOIN paper, ORDER BY paper_id):     ~840 ms
Flask Python: row → dict × 524k + JSON encode:        ~5,100 ms   <- dominant
Network (local, 109 MB):                                  ~20 ms
Browser JSON.parse(109 MB):                          ~1,500-3,000 ms
React: normalize + sourceIndices precompute:           ~150-300 ms
regl-scatterplot init + first GPU upload + draw:       ~500-1,500 ms
────────────────────────────────────────────────────────────────
Total wall-clock:                                       ~8-11 s
```

~85% of wall-clock is Flask building the JSON list of dicts in Python.
The DB itself is fast (840 ms returns every row). The network is trivial.
The browser then spends another 1.5–3 s parsing the 109 MB string before
React sees any data.

Beyond the pure performance win, streaming gives us a "cloud fills in"
animation that's both pleasant and informative — the user sees content
within ~100 ms instead of staring at a spinner.

## Approach

Replace the JSON dump with **NDJSON over a streaming response**. Backend
yields one row per line as PostgreSQL emits them; frontend reads the
stream, parses lines as they arrive, and incrementally pushes batches into
the renderer.

### Wire format

Each NDJSON line is one of:

```jsonc
// First line: header with totals and the data-space bounding box.
// The bounding box lets the frontend normalize each point as it arrives
// without buffering them all to compute min/max.
{"projection": "pacmap_v1", "total": 524604, "bbox": [xmin, ymin, xmax, ymax]}

// Every subsequent line: one point.
{"paper_id": "1304.5893", "title": "Conceptual...", "source": "arxiv", "x": 0.41, "y": 3.33}
```

Trailing newline after every line. `Content-Type: application/x-ndjson`.

The header line lives in the same response so the frontend doesn't need
a separate HEAD request. Alternative: embed it in a `Trailers` header,
but Werkzeug + Next dev proxy don't reliably surface those.

### Backend changes (`src/oversight/flask_app.py`)

Replace the current `points = [...]` list build with a generator that
streams from a **server-side cursor** so psycopg doesn't buffer the full
result set in Python before yielding the first row:

```python
from flask import Response, stream_with_context
import json

@app.get("/api/atlas")
def atlas() -> Response | tuple[dict[str, Any], int]:
    # ... param parsing identical to today ...

    fmt = request.args.get("format", "json").lower()
    if fmt not in {"json", "ndjson"}:
        return {"error": "format must be 'json' or 'ndjson'"}, 400

    if fmt == "json":
        # Existing implementation — keep for compatibility / small projections.
        return _atlas_json(projection, viewport, limit), 200

    # NDJSON path.
    @stream_with_context
    def generate() -> Iterator[bytes]:
        # We need a fresh connection here (not the shared _neighbors_conn)
        # so the server-side cursor isn't entangled with other requests
        # holding the lock. ~25 ms one-time cost, dwarfed by the stream.
        database_url = os.getenv("DATABASE_URL")
        assert database_url is not None
        with psycopg.connect(database_url) as con:
            register_vector(con)
            # First pass: get the bbox + count cheaply. The index on
            # (projection, x, y) makes MIN/MAX fast; COUNT(*) on the
            # filtered subset takes ~100 ms even at 524k.
            with con.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*), MIN(x), MAX(x), MIN(y), MAX(y) "
                    "FROM paper_projection_2d WHERE projection = %s",
                    [projection],
                )
                total, xmin, xmax, ymin, ymax = cur.fetchone()
            header = {
                "projection": projection,
                "total": total,
                "bbox": [float(xmin), float(ymin), float(xmax), float(ymax)],
            }
            yield (json.dumps(header) + "\n").encode("utf-8")

            # Second pass: server-side cursor streams rows. itersize
            # controls how many rows psycopg fetches per round-trip;
            # 5000 is a good balance — large enough that round-trip
            # cost amortizes, small enough that the first batch arrives
            # quickly.
            with con.cursor(name="atlas_stream") as cur:
                cur.itersize = 5000
                # Same JOIN as today. Skip ORDER BY paper_id when
                # streaming — paper_id ordering serves no purpose
                # for the streaming animation, and dropping it lets
                # PostgreSQL stream as it scans (avoids a sort).
                cur.execute(
                    "SELECT pp.paper_id, p.title, p.source, pp.x, pp.y "
                    "FROM paper_projection_2d AS pp "
                    "JOIN paper AS p ON p.paper_id = pp.paper_id "
                    "WHERE pp.projection = %s LIMIT %s",
                    [projection, limit],
                )
                for pid, title, source, x, y in cur:
                    yield (json.dumps({
                        "paper_id": pid, "title": title, "source": source,
                        "x": float(x), "y": float(y),
                    }) + "\n").encode("utf-8")

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        direct_passthrough=True,
    )
```

#### Gotchas

- **`stream_with_context` is required.** Without it, the generator runs
  outside the request context and accessing `request.args` (or anything
  Flask) inside the generator would 500. We do all param parsing before
  the generator is constructed, so we'd be OK either way, but the
  decorator also keeps the connection-teardown semantics sane.
- **`direct_passthrough=True`** disables Werkzeug's auto-buffering. Without
  it, Werkzeug collects the whole iterator before sending — defeating the
  point.
- **Production server matters.** Werkzeug's dev server flushes per yield
  (`werkzeug.serving.WSGIServer`). gunicorn's sync workers buffer the full
  response by default; use `--worker-class gthread` or `gevent`. The
  Dockerfile.api currently uses the dev server (`oversight serve`); we'd
  want to add a deployment note when this lands.
- **Server-side cursor naming.** `cur = con.cursor(name="atlas_stream")`
  is what makes psycopg use a server-side cursor (`DECLARE ... CURSOR`).
  Anonymous cursors buffer everything client-side.
- **`COUNT(*)` for the header costs ~50–100 ms** at 524k with the index.
  Could be skipped (omit `total` from the header) if we want the user to
  see content even faster, at the cost of losing the progress percentage.
- **Drop `ORDER BY paper_id`** in the streaming path. PostgreSQL has to
  buffer the entire result set to sort it before emitting the first row,
  which negates the streaming benefit. Either accept index-scan order
  (whatever the planner picks) or `ORDER BY pp.x` so the cloud fills in
  spatially (left-to-right) — that's a more meaningful animation but
  costs a sort.
- **One connection per stream.** Don't reuse `_neighbors_conn` — a
  server-side cursor pins the connection for the duration of the stream,
  and the lock would block every other endpoint for 5+ seconds.
- **JSON encoding per row.** `json.dumps(...)` for 524k small dicts is
  ~1.5–2 s on its own, faster than the equivalent `json.dumps(big_list)`
  because each call is independent and CPython can inline the small
  cases. If we want to push further, switch to `orjson` (typical 2–3× on
  this workload), but plain `json` should already cut server time
  dramatically.

### Frontend changes (`frontend/pages/atlas.tsx`)

Replace the `fetch(...).json()` call with a streaming reader. The render
loop already supports incremental redraws (`scatter.draw(currentPoints)`
re-uploads the buffer, which is fine for periodic appends).

```ts
async function streamAtlas(
  projection: string,
  signal: AbortSignal,
  onHeader: (header: AtlasHeader) => void,
  onBatch: (batch: AtlasPoint[]) => void,
): Promise<void> {
  const resp = await fetch(
    `/api/atlas?projection=${encodeURIComponent(projection)}&format=ndjson`,
    { signal },
  );
  if (!resp.ok || !resp.body) {
    throw new Error(`atlas stream failed (${resp.status})`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let header: AtlasHeader | null = null;
  let batch: AtlasPoint[] = [];

  // Tune for redraw cost. At 524k points, a full scatter.draw() takes
  // ~100-300 ms. Flushing every 25k rows gives ~20 redraws total, which
  // is enough animation steps without each redraw stalling the main
  // thread for too long.
  const BATCH_SIZE = 25000;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const newline = buf.lastIndexOf("\n");
    if (newline < 0) continue;
    const complete = buf.slice(0, newline);
    buf = buf.slice(newline + 1);
    for (const line of complete.split("\n")) {
      if (!line) continue;
      const parsed = JSON.parse(line);
      if (!header) {
        // First line is always the header.
        header = parsed as AtlasHeader;
        onHeader(header);
        continue;
      }
      batch.push(parsed as AtlasPoint);
      if (batch.length >= BATCH_SIZE) {
        onBatch(batch);
        batch = [];
      }
    }
  }
  // Flush trailing partial batch + any leftover (header arrives alone if
  // the response is just the header line, which shouldn't happen but
  // defensively).
  if (buf.trim()) {
    try { batch.push(JSON.parse(buf) as AtlasPoint); } catch { /* incomplete */ }
  }
  if (batch.length > 0) onBatch(batch);
}
```

In `AtlasPage`:

```ts
const [points, setPoints] = useState<AtlasPoint[]>([]);
const [header, setHeader] = useState<AtlasHeader | null>(null);
const pointsRef = useRef<AtlasPoint[]>([]);
pointsRef.current = points;

useEffect(() => {
  const ctrl = new AbortController();
  streamAtlas(
    projection,
    ctrl.signal,
    (h) => setHeader(h),
    (batch) => {
      // Append into the points array. We use functional setState to
      // avoid races with concurrent batches arriving close together.
      setPoints((prev) => prev.concat(batch));
    },
  ).catch((err) => {
    if (err.name !== "AbortError") setError(String(err));
  });
  return () => ctrl.abort();
}, [projection]);
```

#### Normalization

Today `normalizePoints` computes min/max over the full array. Streaming
breaks that: each batch arrives without knowing the global span. Two
viable approaches:

1. **Use the bbox from the header line.** The backend computes
   `MIN(x), MAX(x), MIN(y), MAX(y)` cheaply (server-side cursor, indexed)
   and the frontend uses those constants for every point. Cleanest —
   `normalizePoints` becomes pure-functional per row, no cross-point
   dependencies, and we can precompute the scale once.

2. **Re-normalize on every batch and re-upload.** Worse: each redraw
   subtly shifts the visible cloud as outliers arrive late.

Go with (1). The change to `normalizePoints` is small:

```ts
function makeNormalizer(bbox: [number, number, number, number]) {
  const [xmin, ymin, xmax, ymax] = bbox;
  const span = Math.max(xmax - xmin, ymax - ymin) || 1;
  const cx = (xmin + xmax) / 2;
  const cy = (ymin + ymax) / 2;
  const scale = 1.8 / span;
  return (p: AtlasPoint): [number, number] => [
    (p.x - cx) * scale,
    (p.y - cy) * scale,
  ];
}
```

#### Incremental redraw

The existing scatter init is gated on `normalized.length > 0`. Replace
that with: create the scatter once on first batch (or on header arrival
with `await scatter.draw([])`), then re-call `scatter.draw(allPoints)`
on every batch growth.

`drawInflightRef` already serializes draws — keep it, the existing
queue-on-pending pattern handles batch overlap correctly. The redraw
effect's dependency becomes `[points, normalized]`; we already memoize
`normalizedHighlighted` on `[normalized, selectedIndices, highlightCategory]`,
which fires naturally as `points` grows.

#### Search and filter during load

Both should keep working — `indexByPaperId` rebuilds as `points` grows
(O(N) per batch, total O(N × batches) which is acceptable at our scale).
Search results are filtered against this map at render time, so if the
user searches before all points have arrived, only the already-loaded
subset is highlightable. Acceptable trade-off; we can show a "(partial,
still loading)" badge in the dropdown if we want to be polite.

The legend filter via `scatter.filter([indices])` works incrementally
because `visibleIndices` is recomputed from the current `points` length,
not from a fixed snapshot.

## Performance projections

```
Time to first byte (header):                     ~150 ms (DB COUNT + bbox)
Time to first paint (1 batch of 25k):            ~400-600 ms
Time to fully drawn:                             ~6-8 s (likely faster
                                                  than the 8-11 s today
                                                  because Python is no
                                                  longer doing a giant
                                                  list build)
Memory peak (server):                            ~constant (cursor)
Memory peak (browser):                           halved (no 109 MB string)
```

The user perceives "instant" because content appears at ~500 ms, then
watches the cloud fill in.

## Test strategy

- **Unit**: a Python test that hits `/api/atlas?format=ndjson` with the
  Flask test client, splits by `\n`, asserts header has `total/bbox` and
  every subsequent line parses to a point with the expected keys. Run
  against a tiny fixture projection so it doesn't take 5 s.
- **Integration**: a frontend test that mocks a small NDJSON response,
  feeds it through `streamAtlas`, asserts `onHeader` fires once before
  any `onBatch`, and that `onBatch` is called with growing batches.
- **Manual / CDP**: load `/atlas`, watch the cloud animate in. Verify
  filter and search work mid-load.

## Migration steps

1. **Add the NDJSON path behind `?format=ndjson`** — the existing JSON
   path stays as-is. No frontend changes yet. Test with curl:
   `curl -N localhost:5001/api/atlas?projection=pacmap_v1&format=ndjson | head`.
2. **Wire the frontend `streamAtlas` helper** but keep it behind a flag
   (`?stream=1` query param). Both paths coexist for a session of
   side-by-side testing.
3. **Flip the default** when the streaming path is stable. Keep the
   one-shot JSON path for cases where a single blob is genuinely
   wanted (server-side rendering, scripts).
4. **Tune `BATCH_SIZE` and `itersize`** based on observed metrics. The
   sweet spot will shift between dev (local Flask) and prod (gunicorn +
   real network).
5. **Eventually delete the bulk JSON path** once nothing depends on it.

## Open questions / next-session work

- Should we order by `pp.x` so the cloud fills left-to-right rather than
  in index-scan order? It's a more meaningful animation; costs a sort
  (~few hundred ms before the first row).
- If we go to deck.gl (see `deckgl-render.md`), streaming and the
  IconLayer/ScatterplotLayer migration intersect — we want to think
  about whether deck.gl's incremental data binding gives us anything
  better than the per-batch `scatter.draw` redraw we have here.
- Worth measuring whether `orjson` is worth the dep. The streaming win
  already comes from "first byte arrives early," not from total Python
  CPU; `orjson` would mainly help if the user's machine ever serves a
  4M-point projection.
