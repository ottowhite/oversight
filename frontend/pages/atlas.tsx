import Head from "next/head";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
} from "react";
import {
  streamAtlas,
  makeNormalizer,
  type AtlasPoint,
  type AtlasHeader,
} from "../lib/streamAtlas";

// regl-scatterplot touches WebGL/canvas/window at import time so it must
// be loaded only in the browser. Mirrors the lazy-import dance graph.tsx
// uses for react-force-graph-2d.
let cachedCreateScatterplot:
  | ((opts: Record<string, unknown>) => ScatterplotApi)
  | null = null;
let createScatterplotPromise: Promise<
  (opts: Record<string, unknown>) => ScatterplotApi
> | null = null;
function loadCreateScatterplot(): Promise<
  (opts: Record<string, unknown>) => ScatterplotApi
> {
  if (cachedCreateScatterplot)
    return Promise.resolve(cachedCreateScatterplot);
  if (createScatterplotPromise) return createScatterplotPromise;
  createScatterplotPromise = import("regl-scatterplot").then((mod) => {
    // ESM default export is the createScatterplot factory.
    cachedCreateScatterplot = (mod as unknown as { default: typeof cachedCreateScatterplot })
      .default as (opts: Record<string, unknown>) => ScatterplotApi;
    return cachedCreateScatterplot!;
  });
  return createScatterplotPromise;
}

// Trimmed-down scatterplot API surface — we only use draw/destroy and
// the pointOver/pointOut/select events. Full types live in the
// regl-scatterplot package; we keep this local to avoid leaking its
// (large) Properties shape into our component file.
type ScatterplotApi = {
  draw: (points: number[][], opts?: Record<string, unknown>) => Promise<void>;
  destroy: () => void;
  subscribe: (event: string, cb: (payload: unknown) => void) => void;
  unsubscribe: (event: string, cb: (payload: unknown) => void) => void;
  set: (props: Record<string, unknown>) => void;
  // filter(indices) restricts what's drawn to those original point
  // indices (so click → paper_id lookup via list[idx] still works).
  // unfilter() restores the full set.
  filter: (
    pointIdxs: number[],
    opts?: { preventEvent?: boolean },
  ) => Promise<void> | void;
  unfilter: (opts?: { preventEvent?: boolean }) => Promise<void> | void;
  // select() restricts the "active" highlight to those indices — they
  // get drawn in pointColorActive. preventEvent stops it from firing
  // the 'select' event back at our own subscriber.
  select: (
    pointIdxs: number[],
    opts?: { merge?: boolean; remove?: boolean; preventEvent?: boolean },
  ) => Promise<void> | void;
  deselect: (opts?: { preventEvent?: boolean }) => Promise<void> | void;
};

// ---------------------------------------------------------------------------
// API contract.
// ---------------------------------------------------------------------------

// AtlasPoint is imported from ../lib/streamAtlas — keep AtlasResponse here
// since it's the shape of the legacy JSON endpoint and only the JSON path
// uses it.
type AtlasResponse = {
  projection: string;
  count: number;
  points: AtlasPoint[];
};

// A single dropdown entry returned by /api/search.
type SearchResult = {
  paper_id: string;
  title: string;
  source?: string | null;
  paper_date?: string | null;
  authors?: string[];
};

// Rich paper metadata fetched lazily on hover. Mirrors what
// /api/papers/<id> returns. We don't include this in /api/atlas
// because abstracts would balloon the 18k-point payload from 3.5 MB
// to ~30 MB (and worse on the 940k corpus).
type PaperDetail = {
  paper_id: string;
  title: string;
  abstract?: string | null;
  source?: string | null;
  link?: string | null;
  authors: string[];
  institutions?: string[];
  paper_date?: string | null;
};

// Default projection — full 524k corpus. Users can override with
// ?projection=pacmap_pl_v1 (or any other future projection name) to
// see a smaller slice; the page reads the query string on mount.
const DEFAULT_PROJECTION = "pacmap_v1";

// Stable color palette keyed by source. Order matters — the first
// distinct source the data exposes lands on COLOR_PALETTE[0], etc.
// All colours are picked to read against the Vercel-style #000 bg.
// The full corpus has ~20 sources, so this list is generously sized;
// the FALLBACK_COLOR below is reserved for anything past the end.
const COLOR_PALETTE = [
  "#3b82f6", // blue
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ef4444", // red
  "#a855f7", // violet
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#84cc16", // lime
  "#f97316", // orange
  "#14b8a6", // teal
  "#eab308", // yellow
  "#8b5cf6", // indigo
  "#22d3ee", // sky
  "#f43f5e", // rose
  "#65a30d", // lime-dark
  "#d946ef", // fuchsia
  "#0ea5e9", // sky-strong
  "#16a34a", // green
  "#dc2626", // red-strong
  "#7c3aed", // purple
  "#facc15", // yellow-strong
  "#0891b2", // cyan-dark
];
const FALLBACK_COLOR = "#9ca3af"; // gray-400, for unknown sources

function buildSourceColorIndex(
  points: AtlasPoint[],
): { byIndex: number[]; legend: { source: string; color: string }[] } {
  // Discover the unique sources in insertion order so the legend stays
  // stable across page refreshes (the API orders by paper_id).
  const seen = new Map<string, number>();
  for (const p of points) {
    const key = p.source ?? "unknown";
    if (!seen.has(key)) seen.set(key, seen.size);
  }
  const legend = Array.from(seen.entries()).map(([source, idx]) => ({
    source,
    color: idx < COLOR_PALETTE.length ? COLOR_PALETTE[idx] : FALLBACK_COLOR,
  }));
  const byIndex = points.map((p) => seen.get(p.source ?? "unknown") ?? 0);
  return { byIndex, legend };
}

// regl-scatterplot expects points in normalized device coords ([-1, 1] on
// both axes by default). We rescale from data space → unit-square so
// the plot fills the viewport regardless of how PaCMAP placed things.
function normalizePoints(
  raw: AtlasPoint[],
  categoryByIndex: number[],
): number[][] {
  if (raw.length === 0) return [];
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of raw) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  // Preserve aspect ratio by using the larger span as the divisor.
  const span = Math.max(spanX, spanY);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  // 1.8 keeps a small margin so points don't graze the canvas edge.
  const scale = 1.8 / span;
  return raw.map((p, i) => [
    (p.x - cx) * scale,
    (p.y - cy) * scale,
    categoryByIndex[i],
  ]);
}

export default function AtlasPage() {
  // Initial projection: ?projection=<name> wins over the default. We
  // read from window.location so it works without router.isReady wait.
  const [projection] = useState<string>(() => {
    if (typeof window === "undefined") return DEFAULT_PROJECTION;
    const sp = new URLSearchParams(window.location.search);
    return sp.get("projection")?.trim() || DEFAULT_PROJECTION;
  });
  // Stream mode is a one-shot, read-once query flag. We hold it as a
  // const (not state) so the JSON vs NDJSON code paths can fork cleanly
  // at effect-level without React fighting us about deps.
  const streamMode: boolean =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("stream") === "1";
  // In JSON mode `points === null` means "still loading"; in stream mode
  // we initialise to [] and use `header === null` as the loading sentinel
  // instead — points genuinely starts empty and grows batch-by-batch.
  const [points, setPoints] = useState<AtlasPoint[] | null>(
    streamMode ? [] : null,
  );
  const [header, setHeader] = useState<AtlasHeader | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(
    null,
  );
  // Sources that the user has clicked off in the legend. Empty Set =
  // show everything. We key by source string (not category index) so
  // toggles survive a points refetch / projection change. arxiv is
  // hidden by default — at the full-corpus scale it dominates 80%+ of
  // the cloud and washes out the conference clusters; the user can
  // always click it back on from the legend.
  const [hiddenSources, setHiddenSources] = useState<Set<string>>(
    () => new Set(["arxiv"]),
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const scatterRef = useRef<ScatterplotApi | null>(null);
  // Serializes scatter.draw calls — the lib rejects concurrent draws
  // with an "Ignoring draw call on the previous draw call has not yet
  // finished" error, so we await any in-flight draw before issuing a
  // new one.
  const drawInflightRef = useRef<Promise<unknown> | null>(null);
  // Mirrors of state that the post-draw re-filter step reads — we use
  // refs because the redraw effect runs inside an async closure that
  // captures the props at scheduling time, but we want the *latest*
  // filter state at apply time.
  const visibleIndicesRef = useRef<number[]>([]);
  const hiddenSourcesRef = useRef<Set<string>>(new Set());
  // Keep the points list in a ref so event callbacks (registered once)
  // can look up paper_ids without re-subscribing on every render.
  const pointsRef = useRef<AtlasPoint[] | null>(null);
  pointsRef.current = points;

  // Process-local cache of rich paper metadata. Keys are paper_id.
  // A hover may flip over many points in quick succession — without
  // a cache we'd re-fetch the same abstract every time the user wiggles
  // back to a point they already saw.
  const [paperCache, setPaperCache] = useState<Record<string, PaperDetail>>(
    {},
  );
  const paperCacheRef = useRef(paperCache);
  paperCacheRef.current = paperCache;
  // Sidebar display follows hoverPaperId by default; if the user clicks
  // a point, that paper is pinned and overrides subsequent hovers until
  // they either click a different point or hit the X to clear. Mirrors
  // the graph page's "click to latch" behaviour.
  const [hoverPaperId, setHoverPaperId] = useState<string | null>(null);
  const [pinnedPaperId, setPinnedPaperId] = useState<string | null>(null);
  const sidebarPaperId = pinnedPaperId ?? hoverPaperId;

  // Search bar state.
  // - `searchInput` mirrors the input field.
  // - `searchResults` is the dropdown list, fetched (debounced) from
  //   /api/search. Each entry is filtered down to papers that actually
  //   appear in the current atlas — we can't highlight a point that
  //   isn't on the map.
  // - `selectedIds` is the multi-select set of papers the user has
  //   ticked; those points get the white-halo "active" treatment via
  //   regl-scatterplot's select() API.
  const [searchInput, setSearchInput] = useState<string>("");
  const [searchOpen, setSearchOpen] = useState<boolean>(false);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(
    null,
  );
  const [searchLoading, setSearchLoading] = useState<boolean>(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(),
  );
  const searchSeqRef = useRef(0); // protects against out-of-order responses

  // In-flight dedup: a single paper_id won't kick off two fetches if
  // the hover event fires twice in quick succession.
  const inflightDetailRef = useRef<Map<string, Promise<PaperDetail | null>>>(
    new Map(),
  );
  const fetchPaperDetail = useCallback(
    async (paperId: string): Promise<PaperDetail | null> => {
      const cached = paperCacheRef.current[paperId];
      if (cached) return cached;
      const existing = inflightDetailRef.current.get(paperId);
      if (existing) return existing;
      const promise = (async () => {
        try {
          const resp = await fetch(
            `/api/papers/${encodeURI(paperId)}`,
          );
          if (!resp.ok) return null;
          const body = (await resp.json()) as PaperDetail;
          setPaperCache((prev) => ({ ...prev, [paperId]: body }));
          return body;
        } catch {
          return null;
        } finally {
          inflightDetailRef.current.delete(paperId);
        }
      })();
      inflightDetailRef.current.set(paperId, promise);
      return promise;
    },
    [],
  );

  const toggleSource = useCallback((source: string) => {
    setHiddenSources((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }, []);
  const showAllSources = useCallback(() => setHiddenSources(new Set()), []);
  const hideAllSources = useCallback(() => {
    // "Hide all" — but if everything would be hidden, the canvas
    // goes blank; that's fine and reversible, the user can click
    // any legend entry to restore it.
    const all = new Set<string>();
    const list = pointsRef.current;
    if (list) {
      for (const p of list) all.add(p.source ?? "unknown");
    }
    setHiddenSources(all);
  }, []);

  // Fetch points on mount. Two completely separate paths so neither
  // accidentally pessimises the other; we deliberately don't try to
  // unify them.
  useEffect(() => {
    if (streamMode) {
      // NDJSON streaming path: a fresh AbortController per effect run
      // so projection changes / unmount cancel the in-flight fetch
      // cleanly (the underlying ReadableStream propagates abort).
      const ctrl = new AbortController();
      // Reset header + points on (re)entry — a projection change must
      // not show stale geometry from the previous projection while the
      // new stream is in flight.
      setHeader(null);
      setPoints([]);
      (async () => {
        try {
          await streamAtlas(
            projection,
            ctrl.signal,
            (h) => setHeader(h),
            // Functional setState: batches arriving back-to-back must
            // compose. Without `prev =>` we'd race and clobber.
            (batch) => setPoints((prev) => (prev ?? []).concat(batch)),
          );
        } catch (err) {
          // AbortError from the cleanup below is expected — swallow it.
          if ((err as { name?: string } | null)?.name === "AbortError") return;
          setError(String(err));
        }
      })();
      return () => {
        ctrl.abort();
      };
    }
    // Legacy JSON path — unchanged.
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(
          `/api/atlas?projection=${encodeURIComponent(projection)}`,
        );
        if (!resp.ok) {
          throw new Error(`atlas fetch failed (${resp.status})`);
        }
        const body = (await resp.json()) as AtlasResponse;
        if (cancelled) return;
        setPoints(body.points);
      } catch (err) {
        if (cancelled) return;
        setError(String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projection, streamMode]);

  // Map paper_id → atlas index, so checking a result can call
  // scatter.select([idx]) without scanning the full points array.
  const indexByPaperId = useMemo(() => {
    const m = new Map<string, number>();
    if (points) {
      for (let i = 0; i < points.length; i++) m.set(points[i].paper_id, i);
    }
    return m;
  }, [points]);

  // Debounced semantic search. We send the query to /api/search and
  // filter results down to papers that actually appear in the atlas;
  // any others are unhighlightable on this map. The seq counter
  // guards against a slow earlier request landing after a faster
  // later one — a real risk when the user is still typing.
  useEffect(() => {
    const q = searchInput.trim();
    if (!q) {
      setSearchResults(null);
      setSearchLoading(false);
      setSearchError(null);
      return;
    }
    const seq = ++searchSeqRef.current;
    setSearchLoading(true);
    const handle = setTimeout(() => {
      (async () => {
        try {
          // Pass every source flag = true so the embedding search isn't
          // accidentally filtered by the legend toggles. We still keep
          // the legend filter — it controls visibility on the canvas,
          // not which papers are reachable via search.
          const params = new URLSearchParams({
            text: q,
            time_window_days: "99999",
            arxiv: "true",
            ICML: "true",
            NeurIPS: "true",
            ICLR: "true",
            OSDI: "true",
            SOSP: "true",
            ASPLOS: "true",
            ATC: "true",
            NSDI: "true",
            MLSys: "true",
            EuroSys: "true",
            VLDB: "true",
            POPL: "true",
            PLDI: "true",
            ICFP: "true",
            OOPSLA: "true",
            ESOP: "true",
            ECOOP: "true",
            Haskell: "true",
            CC: "true",
          });
          const resp = await fetch(`/api/search?${params.toString()}`);
          if (!resp.ok) throw new Error(`search failed (${resp.status})`);
          const body = (await resp.json()) as { results: SearchResult[] };
          if (seq !== searchSeqRef.current) return; // a newer query won
          // Keep only papers that have a coordinate in the current
          // projection — others can't be highlighted on the map.
          const mapped = body.results.filter((r) =>
            indexByPaperId.has(r.paper_id),
          );
          setSearchResults(mapped);
          setSearchError(null);
        } catch (err) {
          if (seq !== searchSeqRef.current) return;
          setSearchError(String(err));
          setSearchResults([]);
        } finally {
          if (seq === searchSeqRef.current) setSearchLoading(false);
        }
      })();
    }, 280); // small debounce so a fast typist doesn't flood the API
    return () => clearTimeout(handle);
  }, [searchInput, indexByPaperId]);

  const toggleSelected = useCallback((paperId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(paperId)) next.delete(paperId);
      else next.add(paperId);
      return next;
    });
  }, []);
  const clearSelected = useCallback(() => setSelectedIds(new Set()), []);

  // Atlas indices of the currently-selected paper ids. Recomputed
  // when either the selection set or the points layout changes (a
  // projection swap remaps every id → idx).
  const selectedIndices = useMemo(() => {
    const out: number[] = [];
    for (const pid of selectedIds) {
      const idx = indexByPaperId.get(pid);
      if (idx !== undefined) out.push(idx);
    }
    return out;
  }, [selectedIds, indexByPaperId]);

  const { byIndex: categoryByIndex, legend } = useMemo(
    () => (points ? buildSourceColorIndex(points) : { byIndex: [], legend: [] }),
    [points],
  );

  // We highlight selected points by repainting them in a special
  // "highlight" colour category (index = legend.length, after all
  // source categories). That index is set in pointColor below at
  // scatterplot init. When the selection set changes, we rebuild the
  // points array with the third column swapped to the highlight
  // category for selected indices and call scatter.draw(...) again.
  //
  // The original implementation used DOM <div> overlay rings
  // positioned via scatter.getScreenPosition. The math broke on
  // devicePixelRatio > 1 and even at dpr=1 the rings drifted ~17px
  // from the underlying dot. Pushing the highlight through regl's
  // own pipeline (recolouring the affected points) is pixel-perfect
  // by construction.
  const HIGHLIGHT_COLOR = "#ffd84a";
  const highlightCategory = legend.length;

  // Base "no-highlights" points array — exposed as a memo so the
  // selection-aware redraw below can mutate just the affected rows
  // without re-running normalize/build on every toggle.
  //
  // Stream-mode caveat: we can't do the JSON-path's global min/max
  // scan because the data arrives in batches; instead the backend's
  // header carries the bbox of the full corpus and we feed that to
  // makeNormalizer once. While `header` is null we return [] so the
  // canvas just shows the loading state — the first batch's arrival
  // will already have set the header (the stream contract guarantees
  // header-then-points order).
  //
  // Known cost (acceptable, documented): buildSourceColorIndex above
  // discovers sources in insertion order, so a source that first
  // appears in batch N lands in the legend at position N rather than
  // wherever it would land under a full-corpus scan. We could fix this
  // by ordering on the backend but that would defeat the point of
  // streaming.
  const normalized = useMemo(() => {
    if (streamMode) {
      if (!header || !points || points.length === 0) return [];
      const norm = makeNormalizer(header.bbox);
      const out: number[][] = new Array(points.length);
      for (let i = 0; i < points.length; i++) {
        const [nx, ny] = norm(points[i]);
        out[i] = [nx, ny, categoryByIndex[i]];
      }
      return out;
    }
    return points ? normalizePoints(points, categoryByIndex) : [];
  }, [points, categoryByIndex, streamMode, header]);

  // Points array with selected rows recoloured to highlightCategory.
  // We allocate fresh rows for the changed indices and reuse the
  // shared rows otherwise to keep allocation cost proportional to the
  // selection size rather than the corpus size.
  const normalizedHighlighted = useMemo(() => {
    if (normalized.length === 0) return normalized;
    if (selectedIndices.length === 0) return normalized;
    const next = normalized.slice();
    for (const idx of selectedIndices) {
      const row = next[idx];
      if (!row) continue;
      // Clone just the rows we change — the rest stay reference-equal,
      // which regl-scatterplot handles fine since draw() does its own
      // copy into a GPU buffer.
      next[idx] = [row[0], row[1], highlightCategory];
    }
    return next;
  }, [normalized, selectedIndices, highlightCategory]);

  // Precompute per-source index arrays once per points load. Toggling
  // a source then becomes a flat concat of the *visible* source
  // buckets — O(unique_sources) rather than O(N) per toggle. At 524k
  // points the savings turn a ~2.5s naive recompute into a sub-400ms
  // round-trip including the scatter.filter() upload.
  const sourceIndices = useMemo(() => {
    const m = new Map<string, Uint32Array>();
    if (!points) return m;
    const counts = new Map<string, number>();
    for (const p of points) {
      const s = p.source ?? "unknown";
      counts.set(s, (counts.get(s) ?? 0) + 1);
    }
    const writers = new Map<string, { buf: Uint32Array; i: number }>();
    for (const [s, n] of counts) {
      writers.set(s, { buf: new Uint32Array(n), i: 0 });
    }
    for (let i = 0; i < points.length; i++) {
      const w = writers.get(points[i].source ?? "unknown");
      if (w) {
        w.buf[w.i++] = i;
      }
    }
    for (const [s, w] of writers) m.set(s, w.buf);
    return m;
  }, [points]);

  // Compose visible indices from the precomputed buckets, dropping any
  // source that the user has toggled off. Returns a single number[]
  // because regl-scatterplot's filter() doesn't accept typed arrays.
  const visibleIndices = useMemo(() => {
    if (!points) return [] as number[];
    if (hiddenSources.size === 0) return [] as number[];
    let total = 0;
    const include: Uint32Array[] = [];
    for (const [src, buf] of sourceIndices) {
      if (hiddenSources.has(src)) continue;
      include.push(buf);
      total += buf.length;
    }
    const merged: number[] = new Array(total);
    let off = 0;
    for (const buf of include) {
      for (let i = 0; i < buf.length; i++) merged[off++] = buf[i];
    }
    return merged;
  }, [points, hiddenSources, sourceIndices]);
  visibleIndicesRef.current = visibleIndices;
  hiddenSourcesRef.current = hiddenSources;

  // Track mouse position so the hover tooltip can follow the cursor.
  // Using a single listener on the container is cheap and avoids
  // wiring this through regl-scatterplot's event system.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    };
    const onLeave = () => setMousePos(null);
    el.addEventListener("mousemove", onMove);
    el.addEventListener("mouseleave", onLeave);
    return () => {
      el.removeEventListener("mousemove", onMove);
      el.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  // Build / rebuild the scatterplot whenever points change.
  useEffect(() => {
    if (!normalized.length || !canvasRef.current || !containerRef.current)
      return;

    let cancelled = false;
    let scatter: ScatterplotApi | null = null;

    (async () => {
      const createScatterplot = await loadCreateScatterplot();
      if (cancelled) return;
      const container = containerRef.current!;
      const canvas = canvasRef.current!;
      // regl-scatterplot's createRegl reads the canvas's intrinsic
      // size (canvas.width/height — the attribute, not the CSS prop)
      // when it allocates the WebGL backing buffer. Our canvas is
      // sized via Tailwind classes ("h-full w-full"), which only sets
      // CSS dims; the attribute width/height default to 300x150. If we
      // don't seed those, regl can fail to acquire a GL context (or
      // allocate a 300x150 buffer that we then stretch). Set them
      // explicitly to the container's measured size before init.
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));

      const sourceColors = legend.map((l) => l.color);
      // Final pointColor list: source palette + the highlight slot.
      // colorBy='valueA' (the 3rd column on each point) indexes into
      // this list, so selected points encoded as highlightCategory
      // (= legend.length) render in HIGHLIGHT_COLOR.
      const pointColors =
        sourceColors.length > 0
          ? [...sourceColors, HIGHLIGHT_COLOR]
          : [FALLBACK_COLOR, HIGHLIGHT_COLOR];
      scatter = createScatterplot({
        canvas,
        // 'auto' tells the lib to use the canvas's own dimensions
        // rather than overriding them. Combined with the explicit
        // canvas.width/height above, this gives a correctly-sized
        // backing buffer on the first paint.
        width: "auto",
        height: "auto",
        // Source category lives in points[i][2]; without colorBy the
        // renderer ignores it and paints every point with pointColor[0].
        // 'valueA' is the encoding name for the 3rd column.
        // The 3rd column (valueA) drives colour, size, and opacity so
        // selected papers (encoded as highlightCategory) jump out from
        // the surrounding cloud in all three channels at once. Each
        // *By: 'valueA' is required to actually wire the per-category
        // array into the GPU encoding (esm.js DEFAULT_*_BY = null).
        colorBy: "valueA",
        sizeBy: "valueA",
        opacityBy: "valueA",
        pointColor: pointColors,
        pointColorActive: "#ffffff",
        pointColorHover: "#ffffff",
        // Per-category size and opacity arrays. Highlight category
        // gets ~10x the cloud point size and full opacity (1.0 vs
        // 0.55) so it reads as obvious bright yellow against the
        // surrounding cloud — no shape change needed.
        pointSize: [
          ...sourceColors.map(() => 3),
          30, // highlight slot — ~10x the cloud size, very obvious
        ],
        opacity: [
          ...sourceColors.map(() => 0.55),
          1.0, // highlight slot — fully opaque
        ],
        // asinh keeps point size manageable at the full-corpus zoom
        // levels — without it, zooming out at 524k smears the cloud
        // into a solid blob.
        pointScaleMode: "asinh",
        pointSizeSelected: 14,
        pointOutlineWidth: 3,
        backgroundColor: [0, 0, 0, 1],
      });
      scatterRef.current = scatter;
      // First draw uses the highlighted variant so any initial
      // selection (e.g. restored from URL state in future) is shown
      // immediately. The dedicated selection effect handles subsequent
      // changes. We track the inflight draw promise so the selection
      // effect doesn't fire a concurrent draw and trip regl's
      // "previous draw not finished" guard.
      const initDraw = Promise.resolve(scatter.draw(normalizedHighlighted));
      drawInflightRef.current = initDraw;
      try {
        await initDraw;
      } finally {
        if (drawInflightRef.current === initDraw) drawInflightRef.current = null;
      }
      // Re-apply the current filter immediately after the initial draw
      // so a points refetch (or projection change) preserves the user's
      // toggles. The standalone filter effect handles subsequent flips.
      if (hiddenSources.size > 0) {
        const list = pointsRef.current ?? [];
        const idxs: number[] = [];
        for (let i = 0; i < list.length; i++) {
          if (!hiddenSources.has(list[i].source ?? "unknown")) idxs.push(i);
        }
        scatter.filter(idxs);
      }

      const onOver = (idx: unknown) => {
        if (typeof idx !== "number") return;
        setHoverIdx(idx);
        const list = pointsRef.current;
        if (!list || idx < 0 || idx >= list.length) return;
        const pid = list[idx].paper_id;
        // Latch the sidebar onto this paper id immediately so the panel
        // re-renders with a header (and a "Loading…" body) while the
        // fetch is in flight. fetchPaperDetail dedups in-flight calls.
        setHoverPaperId(pid);
        void fetchPaperDetail(pid);
      };
      const onOut = () => setHoverIdx(null);
      const onSelect = (payload: unknown) => {
        const pts = (payload as { points?: number[] } | undefined)?.points;
        if (!pts || pts.length === 0) return;
        const idx = pts[0];
        const list = pointsRef.current;
        if (!list || idx < 0 || idx >= list.length) return;
        const paperId = list[idx].paper_id;
        // Pin this paper to the sidebar instead of navigating away —
        // the user can keep panning the atlas while the chosen paper
        // stays put for reference. The hover state still updates the
        // sidebar normally; the pin "wins" via the sidebarPaperId
        // fallthrough (pinned ?? hover).
        setPinnedPaperId(paperId);
        void fetchPaperDetail(paperId);
        // regl-scatterplot's internal "active" point set is now
        // unused (search highlights go through the per-point colour
        // encoding instead), so we deselect to suppress the white
        // pointColorActive halo that would otherwise flash on click.
        scatter?.deselect({ preventEvent: true });
      };
      scatter.subscribe("pointOver", onOver);
      scatter.subscribe("pointOut", onOut);
      scatter.subscribe("select", onSelect);
    })().catch((err) => {
      console.error("[atlas] failed to init scatterplot", err);
      setError(String(err));
    });

    // Resize: when the container changes size, push the new dims into
    // both the canvas backing buffer and the scatter. Without the
    // canvas resize, the buffer stays at its init dims and the points
    // get stretched. ResizeObserver fires on first hookup as well, so
    // this also handles the initial layout cleanly.
    const ro = new ResizeObserver((entries) => {
      if (!scatter || !canvasRef.current) return;
      const entry = entries[0];
      if (!entry) return;
      const w = entry.contentRect.width;
      const h = entry.contentRect.height;
      const ratio = window.devicePixelRatio || 1;
      canvasRef.current.width = Math.max(1, Math.floor(w * ratio));
      canvasRef.current.height = Math.max(1, Math.floor(h * ratio));
      scatter.set({ width: w, height: h });
      // Resize can clobber the active filter (the lib re-does scale
      // computation and bookkeeping). Re-apply from the current ref
      // so toggled-off sources don't reappear after a layout shift.
      if (hiddenSourcesRef.current.size === 0) {
        scatter.unfilter();
      } else {
        scatter.filter(visibleIndicesRef.current);
      }
    });
    ro.observe(containerRef.current!);

    return () => {
      cancelled = true;
      ro.disconnect();
      if (scatter) scatter.destroy();
      scatterRef.current = null;
    };
    // hiddenSources intentionally omitted: we only read it once at
    // init for the initial filter; subsequent toggles are handled by
    // the dedicated filter effect below, so re-running this whole init
    // on every toggle would needlessly tear down the GL context.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalized, legend, fetchPaperDetail]);

  // Apply the legend filter to the live scatterplot. We do this in a
  // separate effect (rather than during init) so toggling sources
  // doesn't tear down and rebuild the GL context — that would be slow
  // and would reset the camera pan/zoom.
  useEffect(() => {
    const scatter = scatterRef.current;
    if (!scatter) return;
    if (hiddenSources.size === 0) {
      scatter.unfilter();
    } else {
      scatter.filter(visibleIndices);
    }
  }, [visibleIndices, hiddenSources]);

  // Apply the search multi-select to the live scatterplot by redrawing
  // with the highlighted points array (selected rows have category set
  // to highlightCategory). regl-scatterplot's draw() preserves camera
  // pan/zoom, so the only cost is the buffer upload (~hundreds of ms at
  // 524k). This replaces the previous DOM-overlay approach which had
  // DPR/positioning bugs.
  //
  // regl-scatterplot.draw rejects overlapping calls ("Ignoring draw
  // call on the previous draw call has not yet finished"), so we
  // serialize through a small queue: each new selection schedules a
  // redraw that awaits any in-flight draw first.
  useEffect(() => {
    const scatter = scatterRef.current;
    if (!scatter) return;
    if (normalizedHighlighted.length === 0) return;
    let cancelled = false;
    (async () => {
      // If a draw is already in flight, wait for it.
      if (drawInflightRef.current) {
        try {
          await drawInflightRef.current;
        } catch {
          /* ignore — we're about to redraw anyway */
        }
      }
      if (cancelled) return;
      const p = Promise.resolve(scatter.draw(normalizedHighlighted));
      drawInflightRef.current = p;
      try {
        await p;
      } finally {
        if (drawInflightRef.current === p) drawInflightRef.current = null;
      }
      if (cancelled) return;
      // scatter.draw() resets any prior filter() — the lib treats a
      // fresh point buffer as a fresh visibility set. Re-apply the
      // current legend filter so toggling search-select doesn't bring
      // hidden sources back. visibleIndicesRef is kept in sync below.
      const want = visibleIndicesRef.current;
      if (hiddenSourcesRef.current.size === 0) {
        scatter.unfilter();
      } else {
        scatter.filter(want);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [normalizedHighlighted]);

  const hovered = hoverIdx !== null && points ? points[hoverIdx] : null;
  // If the hovered point's source has just been filtered out, suppress
  // the tooltip so we don't show metadata for an invisible point.
  const hoveredSourceVisible =
    hovered && !hiddenSources.has(hovered.source ?? "unknown");

  return (
    <>
      <Head>
        <title>Atlas — Oversight</title>
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
      </Head>
      <main className="grid h-screen grid-rows-[auto,1fr] bg-black text-white">
        <header className="border-b border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40">
          <div className="flex items-center gap-3 px-4 py-3">
            <a
              href="/"
              className="btn btn-ghost btn-sm normal-case text-base-content/80 hover:text-base-content"
            >
              ← Search
            </a>
            <h1 className="text-lg font-semibold">Paper Atlas</h1>
            <span className="text-xs text-base-content/50 ml-2">
              projection: <code>{projection}</code>
              {points
                ? streamMode
                  ? ` · ${points.length.toLocaleString()} / ${
                      header ? header.total.toLocaleString() : "?"
                    } papers`
                  : ` · ${points.length.toLocaleString()} papers`
                : ""}
            </span>
            <a
              href="/graph"
              className="ml-auto btn btn-ghost btn-sm text-base-content/60 hover:text-base-content"
            >
              Graph view
            </a>
          </div>
        </header>

        {/* Two-column body: scatter canvas | paper details sidebar. The
            sidebar is fixed-width so the canvas can hand its full
            measured width to regl-scatterplot without juggling. */}
        <div className="grid min-h-0 grid-cols-[1fr,360px]">
        <div ref={containerRef} className="relative min-h-0 w-full">
          <canvas ref={canvasRef} className="block h-full w-full" />

          {/* Loading state. JSON mode: points === null until the fetch
              lands. Stream mode: points starts as [] (truthy) so we
              instead key off `header === null`, which is the stream's
              equivalent "nothing useful yet" sentinel. */}
          {((streamMode && !header) || (!streamMode && !points)) && !error && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-base-content/70 text-sm">
                Loading atlas…
              </div>
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="card bg-base-200 border border-error/40 p-4 max-w-md">
                <p className="text-sm text-error">Failed to load atlas:</p>
                <p className="text-xs text-base-content/70 mt-1 break-all">
                  {error}
                </p>
              </div>
            </div>
          )}

          {/* Search bar (top-left). Typed query fires a debounced
              semantic search against /api/search; results that exist
              in the current atlas projection appear in the dropdown
              with checkboxes. Checked papers stay highlighted on the
              scatter via regl-scatterplot's select() API even after
              the dropdown closes, so the user can compare the spatial
              positions of multiple chosen papers at once. */}
          <div className="absolute top-3 left-3 w-80 z-20 select-none">
            <div className="card bg-base-200/85 backdrop-blur border border-base-300/60 p-2">
              <div className="flex items-center gap-2">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-4 w-4 text-base-content/40 shrink-0"
                >
                  <path
                    fillRule="evenodd"
                    d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
                    clipRule="evenodd"
                  />
                </svg>
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => {
                    setSearchInput(e.target.value);
                    setSearchOpen(true);
                  }}
                  onFocus={() => setSearchOpen(true)}
                  placeholder="Search papers… (e.g. type theory)"
                  className="flex-1 bg-transparent text-sm placeholder:text-base-content/30 focus:outline-none"
                />
                {searchInput && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchInput("");
                      setSearchResults(null);
                      setSearchOpen(false);
                    }}
                    title="Clear input"
                    className="text-base-content/40 hover:text-base-content"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="h-3.5 w-3.5"
                    >
                      <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" />
                    </svg>
                  </button>
                )}
              </div>
              {selectedIds.size > 0 && (
                <div className="mt-1 flex items-center justify-between text-[11px] text-base-content/60">
                  <span>
                    <span className="text-accent font-semibold">
                      {selectedIds.size}
                    </span>{" "}
                    selected
                  </span>
                  <button
                    type="button"
                    onClick={clearSelected}
                    className="text-base-content/50 hover:text-base-content underline"
                  >
                    clear
                  </button>
                </div>
              )}
            </div>

            {/* Dropdown — only when the input is focused / non-empty. */}
            {searchOpen && searchInput.trim() && (
              <div className="mt-1 card bg-base-200/95 backdrop-blur border border-base-300/60 max-h-[60vh] overflow-y-auto">
                {searchLoading && (
                  <div className="px-3 py-2 text-xs text-base-content/50">
                    Searching…
                  </div>
                )}
                {!searchLoading && searchError && (
                  <div className="px-3 py-2 text-xs text-error">
                    {searchError}
                  </div>
                )}
                {!searchLoading &&
                  !searchError &&
                  searchResults &&
                  searchResults.length === 0 && (
                    <div className="px-3 py-2 text-xs text-base-content/50">
                      No results on this map.
                    </div>
                  )}
                {!searchLoading &&
                  searchResults &&
                  searchResults.length > 0 && (
                    <ul className="divide-y divide-base-300/40">
                      {searchResults.map((r) => {
                        const checked = selectedIds.has(r.paper_id);
                        return (
                          <li key={r.paper_id}>
                            <label className="flex items-start gap-2 px-3 py-2 cursor-pointer hover:bg-base-300/30">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleSelected(r.paper_id)}
                                className="mt-0.5 accent-accent"
                              />
                              <span className="flex-1 min-w-0">
                                <span className="block text-xs text-base-content/90 leading-snug line-clamp-2">
                                  {unicodifySafe(r.title)}
                                </span>
                                <span className="block mt-0.5 text-[10px] text-base-content/40 font-mono truncate">
                                  {r.source || "?"}
                                  {r.paper_date
                                    ? ` · ${formatDateShort(r.paper_date)}`
                                    : ""}
                                  {" · "}
                                  {r.paper_id}
                                </span>
                              </span>
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  )}
              </div>
            )}
          </div>

          {/* Legend — clickable to toggle source visibility */}
          {legend.length > 0 && (
            <div className="absolute top-3 right-3 card bg-base-200/80 backdrop-blur border border-base-300/60 p-2 text-xs select-none">
              <div className="flex items-center justify-between gap-3 mb-1">
                <span className="text-base-content/60 font-semibold">
                  Source
                </span>
                <span className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={showAllSources}
                    title="Show all sources"
                    className="text-[10px] uppercase tracking-wide text-base-content/50 hover:text-base-content"
                  >
                    all
                  </button>
                  <span className="text-base-content/30">·</span>
                  <button
                    type="button"
                    onClick={hideAllSources}
                    title="Hide all sources"
                    className="text-[10px] uppercase tracking-wide text-base-content/50 hover:text-base-content"
                  >
                    none
                  </button>
                </span>
              </div>
              <ul className="space-y-0.5">
                {legend.map((l) => {
                  const hidden = hiddenSources.has(l.source);
                  return (
                    <li key={l.source}>
                      <button
                        type="button"
                        onClick={() => toggleSource(l.source)}
                        title={
                          hidden
                            ? `Show ${l.source}`
                            : `Hide ${l.source}`
                        }
                        className={`w-full flex items-center gap-2 rounded px-1 -mx-1 text-left transition-colors hover:bg-base-300/40 ${
                          hidden ? "opacity-40 line-through" : ""
                        }`}
                      >
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{
                            backgroundColor: hidden ? "transparent" : l.color,
                            boxShadow: hidden
                              ? `inset 0 0 0 1px ${l.color}`
                              : undefined,
                          }}
                        />
                        <span className="text-base-content/80">
                          {l.source}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Hover tooltip — anchored to mouse, follows the cursor */}
          {hovered && hoveredSourceVisible && mousePos && (
            <div
              className="pointer-events-none absolute z-30 max-w-sm card bg-base-200/95 backdrop-blur border border-base-300/60 p-2 text-xs shadow-lg"
              style={{
                left: Math.min(mousePos.x + 12, (containerRef.current?.clientWidth ?? 0) - 320),
                top: Math.min(mousePos.y + 12, (containerRef.current?.clientHeight ?? 0) - 80),
              }}
            >
              <div className="font-semibold leading-snug">{hovered.title}</div>
              <div className="text-base-content/60 mt-1">
                {hovered.source || "unknown source"} · {hovered.paper_id}
              </div>
            </div>
          )}

          {/* Search-selected papers are highlighted by recolouring
              them through regl-scatterplot's own colour-encoding (see
              normalizedHighlighted above) — no DOM overlay required. */}

          {/* Hint */}
          <div className="absolute bottom-3 left-3 text-[10px] text-base-content/40 pointer-events-none">
            Scroll to zoom · drag to pan · click a point to pin it to the
            sidebar
          </div>
        </div>

        {/* Right sidebar — full paper details for the most recently
            hovered (or sidebar-pinned via search) paper. Mirrors the
            graph page's HoverPreview so the two pages feel consistent. */}
        <AtlasSidebar
          paper={
            sidebarPaperId
              ? paperCache[sidebarPaperId] ?? {
                  paper_id: sidebarPaperId,
                  title:
                    pointsRef.current?.find(
                      (p) => p.paper_id === sidebarPaperId,
                    )?.title ?? sidebarPaperId,
                  source:
                    pointsRef.current?.find(
                      (p) => p.paper_id === sidebarPaperId,
                    )?.source ?? null,
                  authors: [],
                }
              : null
          }
          pinned={!!pinnedPaperId && sidebarPaperId === pinnedPaperId}
          loading={!!sidebarPaperId && !paperCache[sidebarPaperId]}
          onClear={() => {
            // Clear-button always removes the pin (if any) and the
            // transient hover latch, so the panel goes back to its
            // "Hover a point…" empty state.
            setPinnedPaperId(null);
            setHoverPaperId(null);
          }}
        />
        </div>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sidebar — pure presentational. Mirrors HoverPreview from graph.tsx so
// hovering a node on either page produces the same rich paper preview.
// ---------------------------------------------------------------------------

function AtlasSidebar({
  paper,
  pinned,
  loading,
  onClear,
}: {
  paper: PaperDetail | null;
  pinned: boolean;
  loading: boolean;
  onClear: () => void;
}) {
  return (
    <aside className="border-l border-base-300/60 bg-base-200/40 min-h-0 flex flex-col">
      <div className="flex items-center justify-between border-b border-base-300/60 px-3 py-2">
        <span className="text-[11px] uppercase tracking-wider font-medium text-base-content/50 flex items-center gap-2">
          Paper details
          {pinned && (
            <span className="text-primary font-semibold normal-case tracking-normal text-[10px] px-1.5 py-0.5 rounded bg-primary/10">
              pinned
            </span>
          )}
        </span>
        {paper && (
          <button
            type="button"
            onClick={onClear}
            title="Clear preview"
            className="btn btn-ghost btn-xs btn-square text-base-content/40 hover:text-base-content"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="h-3.5 w-3.5"
            >
              <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" />
            </svg>
          </button>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        {!paper ? (
          <p className="text-sm text-base-content/40 leading-relaxed">
            Hover a point on the map to preview its details. Click to pin
            the paper here so you can keep panning while it stays put.
          </p>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-2 text-[11px] uppercase tracking-wider font-medium text-base-content/50">
              {paper.source && (
                <span className="font-mono">{paper.source}</span>
              )}
              {paper.paper_date && (
                <span className="font-mono">
                  {formatDateShort(paper.paper_date)}
                </span>
              )}
            </div>

            <h2 className="text-base font-semibold leading-snug text-base-content">
              {paper.link ? (
                <a
                  href={paper.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent hover:underline"
                >
                  {unicodifySafe(paper.title)}
                </a>
              ) : (
                unicodifySafe(paper.title)
              )}
            </h2>

            {paper.authors && paper.authors.length > 0 && (
              <p className="mt-2 text-xs text-base-content/60 leading-relaxed">
                {paper.authors.map(unicodifySafe).join(", ")}
              </p>
            )}

            <p className="mt-1 text-[11px] text-base-content/30 font-mono break-all">
              {paper.paper_id}
            </p>

            {paper.link && (
              <a
                href={paper.link}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary btn-sm mt-3 w-full"
              >
                View paper →
              </a>
            )}

            {loading ? (
              <p className="mt-3 text-sm text-base-content/40 italic">
                Loading abstract…
              </p>
            ) : paper.abstract ? (
              <p className="mt-3 text-sm text-base-content/80 whitespace-pre-wrap leading-relaxed">
                {unicodifySafe(paper.abstract)}
              </p>
            ) : (
              <p className="mt-3 text-sm text-base-content/40 italic">
                No abstract available.
              </p>
            )}
          </>
        )}
      </div>
    </aside>
  );
}

// Small local copies of helpers from graph.tsx. We don't import them
// to avoid coupling the two pages tightly — if the graph version ever
// changes, the atlas version is free to follow at its own pace.

// "2026-01-16" → "Jan 2026". Falls back to the raw string on bad input.
function formatDateShort(iso: string): string {
  const m = /^(\d{4})-(\d{2})-/.exec(iso);
  if (!m) return iso;
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const monthIdx = parseInt(m[2], 10) - 1;
  return `${months[monthIdx] ?? m[2]} ${m[1]}`;
}

// Lightweight TeX-accent decoder so titles like "Sch\"on" render as
// "Schön". Mirrors graph.tsx's unicodify but stripped down — the atlas
// only renders titles/authors, never math.
const TEX_ACCENT_ATLAS: Record<string, string> = {
  "'": "́", // acute
  "`": "̀", // grave
  "^": "̂", // circumflex
  '"': "̈", // diaeresis
  "~": "̃", // tilde
  ".": "̇", // dot above
  "=": "̄", // macron
  c: "̧", // cedilla
};
function unicodifySafe(s: string | null | undefined): string {
  if (!s) return "";
  if (s.indexOf("\\") < 0) return s;
  const re = /\\([c'`^"~.=])(?:\{([A-Za-z])\}|([A-Za-z]))/g;
  let out = s.replace(
    re,
    (_m, accent: string, braced?: string, bare?: string) => {
      const letter = braced ?? bare;
      const combiner = TEX_ACCENT_ATLAS[accent];
      if (!letter || !combiner) return _m;
      return (letter + combiner).normalize("NFC");
    },
  );
  out = out.replace(/\\([A-Za-z])/g, "$1");
  return out;
}
