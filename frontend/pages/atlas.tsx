import Head from "next/head";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
} from "react";

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
  // World-space → screen-space for one point. Returns null when the
  // index is out of range or the scatter hasn't drawn yet.
  getScreenPosition: (
    pointIdx: number,
  ) => [number, number] | undefined | null;
  // get('cameraView') -> Float32Array(16) is the row-major view matrix
  // we need to project arbitrary NDC coords (cluster centroids) to the
  // screen without faking a ghost point. We only need a typed narrow
  // here because pulling regl-scatterplot's full Properties shape into
  // this component would explode our imports.
  get: (property: string) => unknown;
  // Zoom the camera so the rect (in NDC) fills the viewport. Used when
  // the user clicks a cluster label.
  zoomToArea: (
    rect: { x: number; y: number; width: number; height: number },
    opts?: {
      transition?: boolean;
      transitionDuration?: number;
      transitionEasing?: string;
    },
  ) => Promise<void>;
};

// ---------------------------------------------------------------------------
// API contract.
// ---------------------------------------------------------------------------

type AtlasPoint = {
  paper_id: string;
  title: string;
  source: string | null;
  x: number;
  y: number;
};

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

// Default projection: full 524k-paper corpus.
const DEFAULT_PROJECTION = "pacmap_v1";

// Cluster-label payload from /api/atlas/labels.
type ClusterLabel = {
  cluster_id: number;
  centroid: [number, number]; // in PaCMAP world space
  bbox: [number, number, number, number]; // [xmin, ymin, xmax, ymax]
  paper_count: number;
  parent_id: number | null;
  label: string;
  keywords: string[];
};

// Persisted control-panel state. v1 has a single knob (label density);
// stored as a versioned object so adding sliders later doesn't require
// a localStorage migration.
const CONTROL_PANEL_STORAGE_KEY = "atlas/controlPanel/v1";
const DEFAULT_TARGET_COUNT = 6;
const MIN_TARGET_COUNT = 1;
const MAX_TARGET_COUNT = 50;

// Stable color palette keyed by source. Order matters — the first
// distinct source the data exposes lands on COLOR_PALETTE[0], etc.
// All colours are picked to read against the Vercel-style #000 bg.
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

// Project a single NDC-space (x, y) point to canvas-CSS pixels via the
// scatterplot's current view + projectionLocal. Mirrors esm.js ~8377
// (getScreenPosition) but doesn't require a registered point index, so
// we can position cluster-label overlays at arbitrary world coords.
//
// projectionLocal in regl-scatterplot is fromScaling([1/aspect, 1, 1]),
// model is identity for our setup (dataAspectRatio == 1), so:
//   v = view * [x, y, 0, 1]; v[0] *= 1/aspect; v[1] unchanged
//   screen_x = width  * (v[0] + 1) / 2
//   screen_y = height * (0.5 - v[1] / 2)
// Returns null when the projected point falls outside the [-1, 1]^2
// clip-space cube along x or y so callers can cheaply skip off-screen
// labels rather than draw and then hide them.
function projectNdcToScreen(
  ndcX: number,
  ndcY: number,
  view: Float32Array,
  cssWidth: number,
  cssHeight: number,
  cullOffscreen: boolean,
): { x: number; y: number } | null {
  // view is row-major 4x4. The relevant rows for a [x, y, 0, 1] point
  // are the first two: v[0] = m00*x + m01*y + m02*0 + m03*1, etc.
  // regl-scatterplot uses gl-matrix, which is COLUMN-major in storage:
  // index = col*4 + row. We mirror its convention exactly so a
  // copy-paste from esm.js stays correct.
  const vx = view[0] * ndcX + view[4] * ndcY + view[12];
  const vy = view[1] * ndcX + view[5] * ndcY + view[13];
  const aspect = cssWidth / cssHeight;
  // projectionLocal: [1/aspect, 1, 1, 1] scaling
  const cx = vx / aspect;
  const cy = vy;
  if (cullOffscreen && (Math.abs(cx) > 1.05 || Math.abs(cy) > 1.05)) {
    return null;
  }
  return {
    x: (cssWidth * (cx + 1)) / 2,
    y: cssHeight * (0.5 - cy / 2),
  };
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
  const [projection] = useState<string>(DEFAULT_PROJECTION);
  const [points, setPoints] = useState<AtlasPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(
    null,
  );
  // Sources that the user has clicked off in the legend. Empty Set =
  // show everything. We key by source string (not category index) so
  // toggles survive a points refetch / projection change.
  const [hiddenSources, setHiddenSources] = useState<Set<string>>(
    () => new Set(),
  );

  // Control-panel state. We rehydrate from localStorage on mount so a
  // user's label-density preference survives reload, but kick off as
  // the default until the effect below runs (avoids SSR/CSR mismatch).
  const [targetCount, setTargetCount] = useState<number>(DEFAULT_TARGET_COUNT);
  const [controlPanelOpen, setControlPanelOpen] = useState<boolean>(true);
  // Fractal cluster labels — fetched from /api/atlas/labels on viewport
  // change. Keyed by cluster_id so we can smoothly fade in/out as the
  // user pans (labels with stable ids don't flicker).
  const [clusterLabels, setClusterLabels] = useState<
    Record<number, ClusterLabel>
  >({});
  const [pendingClusterIds, setPendingClusterIds] = useState<number[]>([]);
  // Mirror in a ref so the labels-fetch effect (debounced, fires from
  // a setTimeout closure) reads the current target count without
  // re-arming on every keystroke of the slider.
  const targetCountRef = useRef(targetCount);
  targetCountRef.current = targetCount;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const scatterRef = useRef<ScatterplotApi | null>(null);
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

  // localStorage rehydration. Only runs once on mount — afterwards the
  // controlled state is the source of truth and the write-back effect
  // below mirrors it back to disk.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(CONTROL_PANEL_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        targetCount?: number;
        open?: boolean;
      };
      if (typeof parsed.targetCount === "number") {
        const clamped = Math.max(
          MIN_TARGET_COUNT,
          Math.min(MAX_TARGET_COUNT, Math.floor(parsed.targetCount)),
        );
        setTargetCount(clamped);
      }
      if (typeof parsed.open === "boolean") {
        setControlPanelOpen(parsed.open);
      }
    } catch {
      // Corrupt JSON — ignore and let the user reset by clicking once.
    }
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(
        CONTROL_PANEL_STORAGE_KEY,
        JSON.stringify({ targetCount, open: controlPanelOpen }),
      );
    } catch {
      // localStorage may be unavailable in private-browsing or quota'd;
      // we just lose persistence in that case, no fatal.
    }
  }, [targetCount, controlPanelOpen]);

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

  // Fetch points on mount.
  useEffect(() => {
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
  }, [projection]);

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
  // Mirror in a ref so the scatter init's onSelect callback (registered
  // once, captures via closure) can read the current selection without
  // re-subscribing.
  const selectedIndicesRef = useRef<number[]>(selectedIndices);
  selectedIndicesRef.current = selectedIndices;

  // Screen-space positions of selected points, used to render DOM
  // overlay markers on top of the canvas. We can't rely on
  // pointColorActive alone — regl-scatterplot ignores it when colorBy
  // is set (esm.js ~6596), so search highlights would otherwise just
  // be slightly bigger same-coloured dots. The overlay gives us a
  // distinctive yellow ring + drop-shadow regardless of source colour.
  const [overlayPositions, setOverlayPositions] = useState<
    Array<{ idx: number; paperId: string; x: number; y: number }>
  >([]);
  // Bump counter to force a recompute even when selection didn't change
  // (e.g. on pan/zoom or resize the screen positions move).
  const [overlayTick, setOverlayTick] = useState(0);
  useEffect(() => {
    const scatter = scatterRef.current;
    const list = pointsRef.current;
    if (!scatter || !list || selectedIndices.length === 0) {
      setOverlayPositions([]);
      return;
    }
    const ratio = window.devicePixelRatio || 1;
    const next: Array<{
      idx: number;
      paperId: string;
      x: number;
      y: number;
    }> = [];
    for (const idx of selectedIndices) {
      let pos: [number, number] | undefined | null;
      try {
        pos = scatter.getScreenPosition(idx);
      } catch {
        pos = null;
      }
      if (!pos) continue;
      // getScreenPosition returns canvas-buffer pixels (multiplied by
      // DPR). Divide back to CSS pixels so absolute-positioned divs
      // line up with what the user sees.
      next.push({
        idx,
        paperId: list[idx].paper_id,
        x: pos[0] / ratio,
        y: pos[1] / ratio,
      });
    }
    setOverlayPositions(next);
  }, [selectedIndices, overlayTick]);

  const { byIndex: categoryByIndex, legend } = useMemo(
    () => (points ? buildSourceColorIndex(points) : { byIndex: [], legend: [] }),
    [points],
  );

  const normalized = useMemo(
    () => (points ? normalizePoints(points, categoryByIndex) : []),
    [points, categoryByIndex],
  );

  // The PaCMAP-world → NDC transform we apply in normalizePoints. We
  // recompute it here (rather than threading it through that helper's
  // return type) so the cluster-label overlay can project arbitrary
  // PaCMAP coords (cluster centroids, bbox corners) into the same NDC
  // frame regl-scatterplot expects. transform: (x_world, y_world)
  //   -> ((x_world - cx) * scale, (y_world - cy) * scale)
  // Mirror the constants from normalizePoints exactly.
  const worldToNdc = useMemo(() => {
    if (!points || points.length === 0) return null;
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of points) {
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
    const spanX = maxX - minX || 1;
    const spanY = maxY - minY || 1;
    const span = Math.max(spanX, spanY);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const scale = 1.8 / span;
    return { cx, cy, scale };
  }, [points]);

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

      const colors = legend.map((l) => l.color);
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
        colorBy: "valueA",
        pointColor: colors.length > 0 ? colors : [FALLBACK_COLOR],
        // Selected/hover colours. NB: regl-scatterplot's getColors path
        // (esm.js ~6596) ignores pointColorActive when colorBy is set,
        // so we additionally render explicit DOM markers on top of the
        // canvas to make search-selected papers obviously stand out.
        // pointSizeSelected still gives a visible body bump, which acts
        // as a fallback even if our DOM overlay is mis-positioned.
        pointColorActive: "#ffd84a",
        pointColorHover: "#ffffff",
        pointSize: 3,
        pointSizeSelected: 14,
        pointOutlineWidth: 3,
        opacity: 0.7,
        backgroundColor: [0, 0, 0, 1],
      });
      scatterRef.current = scatter;
      await scatter.draw(normalized);
      // Bump the overlay tick once on init so the label-fetch effect
      // (which depends on overlayTick) fires after the first draw.
      // The 'view' event only fires when the camera *changes*, so a
      // freshly-drawn scatter at the default camera wouldn't otherwise
      // emit a signal for the label overlay to latch onto.
      setOverlayTick((t) => t + 1);
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
        // regl-scatterplot also writes its internal selectedPoints
        // when the user clicks. We don't want a stray white halo on
        // the pinned point — the sidebar already communicates the
        // pin — so immediately re-assert the canonical search-driven
        // selection. The dedicated selection effect would do this
        // eventually on the next render, but doing it here avoids a
        // single-frame flash.
        const want = selectedIndicesRef.current;
        if (want.length === 0) scatter?.unfilter && scatter?.deselect?.();
        else scatter?.select(want, { preventEvent: true });
      };
      // The 'view' event fires on every pan/zoom — bump a tick so the
      // DOM overlay markers reposition. Throttling here would be nice
      // but regl already throttles to one event per draw, so the
      // re-render cadence is sane.
      const onView = () => setOverlayTick((t) => t + 1);
      scatter.subscribe("pointOver", onOver);
      scatter.subscribe("pointOut", onOut);
      scatter.subscribe("select", onSelect);
      scatter.subscribe("view", onView);
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
      setOverlayTick((t) => t + 1);
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

  // --- Fractal cluster labels ----------------------------------------------
  //
  // On viewport change we ask the API for ~targetCount labels that fall
  // inside the visible NDC rectangle. The visible NDC rect is the
  // inverse-projection of the canvas corners; we then invert the
  // worldToNdc transform once on the backend's side by converting our
  // computed NDC rect back to PaCMAP-world coords. That keeps the API
  // honest (its bboxes are in world space) and lets us reuse it across
  // projections without per-projection knowledge of the FE transform.
  const fetchClusterLabelsRef = useRef<(includePending: boolean) => void>(
    () => {},
  );
  fetchClusterLabelsRef.current = (includePending: boolean) => {
    const scatter = scatterRef.current;
    const container = containerRef.current;
    if (!scatter || !container || !worldToNdc) return;
    const view = scatter.get("cameraView") as Float32Array | undefined;
    if (!view || view.length < 16) return;

    // Visible NDC rectangle: we need to inverse-project the screen
    // rectangle through projectionLocal and camera.view. Easier path
    // (and good enough for our bbox-intersect test): project the four
    // canvas corners forward and use that as the bounding rect in
    // world space.
    const rect = container.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    // For each canvas corner, undo:
    //   ndc_clip = (screen) -> in [-1, 1]^2
    //   ndc_local = ndc_clip * [aspect, 1]   (undo projectionLocal scale)
    //   ndc_world = inverse(view) * ndc_local
    // Build inverse of the 2x2 affine part of the view matrix (gl-matrix
    // column-major, so [0,4,1,5] correspond to view[0..]):
    const m00 = view[0];
    const m01 = view[4];
    const m10 = view[1];
    const m11 = view[5];
    const tx = view[12];
    const ty = view[13];
    const det = m00 * m11 - m01 * m10;
    if (Math.abs(det) < 1e-9) return;
    const inv00 = m11 / det;
    const inv01 = -m01 / det;
    const inv10 = -m10 / det;
    const inv11 = m00 / det;

    const aspect = w / h;
    function unproject(sx: number, sy: number): [number, number] {
      // screen → clip
      const cx = (2 * sx) / w - 1;
      const cy = 1 - (2 * sy) / h;
      // undo projectionLocal scale
      const lx = cx * aspect;
      const ly = cy;
      // undo view: t = inv * (ndc - translate)
      const dx = lx - tx;
      const dy = ly - ty;
      return [inv00 * dx + inv01 * dy, inv10 * dx + inv11 * dy];
    }
    const corners: [number, number][] = [
      unproject(0, 0),
      unproject(w, 0),
      unproject(0, h),
      unproject(w, h),
    ];
    let nxMin = Infinity;
    let nyMin = Infinity;
    let nxMax = -Infinity;
    let nyMax = -Infinity;
    for (const [nx, ny] of corners) {
      if (nx < nxMin) nxMin = nx;
      if (nx > nxMax) nxMax = nx;
      if (ny < nyMin) nyMin = ny;
      if (ny > nyMax) nyMax = ny;
    }
    // NDC → PaCMAP-world: inverse of worldToNdc
    const wxMin = nxMin / worldToNdc.scale + worldToNdc.cx;
    const wxMax = nxMax / worldToNdc.scale + worldToNdc.cx;
    const wyMin = nyMin / worldToNdc.scale + worldToNdc.cy;
    const wyMax = nyMax / worldToNdc.scale + worldToNdc.cy;

    const params = new URLSearchParams({
      projection,
      viewport: `${wxMin},${wyMin},${wxMax},${wyMax}`,
      target_count: String(targetCountRef.current),
    });
    if (includePending) params.set("include_pending", "true");
    void (async () => {
      try {
        const resp = await fetch(`/api/atlas/labels?${params.toString()}`);
        if (!resp.ok) return;
        const body = (await resp.json()) as {
          labels: ClusterLabel[];
          pending: number[];
        };
        // Merge into the existing map keyed by cluster_id so labels
        // that survive across a small pan keep stable identity (their
        // DOM nodes don't get unmounted/remounted, which avoids the
        // dreaded label-flicker on the mouse-wheel).
        setClusterLabels((prev) => {
          const next: Record<number, ClusterLabel> = {};
          for (const l of body.labels) next[l.cluster_id] = l;
          // Keep old labels for one extra tick so a slow re-fetch
          // doesn't briefly drop the whole overlay; the next fetch
          // will then drop anything not in the fresh slice.
          for (const cid in prev) {
            if (!(cid in next) && body.labels.length === 0) {
              next[cid as unknown as number] = prev[cid];
            }
          }
          return next;
        });
        setPendingClusterIds(body.pending ?? []);
      } catch {
        // Network blip — keep the previous labels rather than blanking
        // the overlay. The next viewport change will retry.
      }
    })();
  };

  // Initial + targetCount-change fetch. Camera-driven refetches are
  // wired through the existing 'view' subscription (overlayTick) below.
  useEffect(() => {
    // Wait until both the scatter and the points are ready; we trigger
    // via overlayTick too, so the very first scatter.draw() will fire
    // a 'view' event that retriggers this effect's body via the
    // separate debounced effect below.
    const handle = setTimeout(() => fetchClusterLabelsRef.current(false), 50);
    return () => clearTimeout(handle);
  }, [projection, normalized, targetCount]);

  // Debounced refetch on camera-view changes. The 'view' subscription
  // in the scatter init bumps overlayTick on every pan/zoom; we listen
  // here and debounce so a smooth wheel-zoom doesn't issue 30 fetches
  // per second.
  useEffect(() => {
    const handle = setTimeout(() => {
      fetchClusterLabelsRef.current(false);
    }, 200);
    return () => clearTimeout(handle);
  }, [overlayTick]);

  // If the backend returned `pending` (more labels needed than fit in
  // the per-request fresh-compute cap), kick off a follow-up call with
  // include_pending=true so the FE eventually shows everything.
  useEffect(() => {
    if (pendingClusterIds.length === 0) return;
    const handle = setTimeout(() => {
      fetchClusterLabelsRef.current(true);
    }, 100);
    return () => clearTimeout(handle);
  }, [pendingClusterIds]);

  // Project each cluster centroid to canvas-CSS pixels for the overlay.
  // Re-runs on every overlayTick (i.e. every regl 'view' event), so
  // labels stay anchored as the user pans/zooms. Cheap: this is a 4x4
  // multiply + 2 divides per label, with target_count <= 50.
  const projectedLabels = useMemo(() => {
    const scatter = scatterRef.current;
    const container = containerRef.current;
    if (!scatter || !container || !worldToNdc) return [];
    let view: Float32Array | undefined;
    try {
      view = scatter.get("cameraView") as Float32Array | undefined;
    } catch {
      view = undefined;
    }
    if (!view || view.length < 16) return [];
    const rect = container.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const out: Array<{
      cluster_id: number;
      label: string;
      paper_count: number;
      x: number;
      y: number;
      bbox: [number, number, number, number];
    }> = [];
    for (const cid of Object.keys(clusterLabels)) {
      const lbl = clusterLabels[cid as unknown as number];
      const ndcX = (lbl.centroid[0] - worldToNdc.cx) * worldToNdc.scale;
      const ndcY = (lbl.centroid[1] - worldToNdc.cy) * worldToNdc.scale;
      const screen = projectNdcToScreen(ndcX, ndcY, view, w, h, true);
      if (!screen) continue;
      out.push({
        cluster_id: lbl.cluster_id,
        label: lbl.label,
        paper_count: lbl.paper_count,
        x: screen.x,
        y: screen.y,
        bbox: lbl.bbox,
      });
    }
    return out;
  }, [clusterLabels, overlayTick, worldToNdc]);

  // Hover a label -> highlight that cluster's papers on the scatter
  // using regl-scatterplot's selection API. We resolve member paper_ids
  // through a tiny per-cluster endpoint, dedup in-flight requests so a
  // hover-as-you-pan interaction doesn't flood the API, and clear the
  // highlight (restoring the search-selection) on mouse-out.
  const clusterMembersCache = useRef<Map<number, string[]>>(new Map());
  const clusterMembersInflight = useRef<Map<number, Promise<string[]>>>(
    new Map(),
  );
  const hoveredClusterRef = useRef<number | null>(null);

  const fetchClusterMembers = useCallback(
    async (cid: number): Promise<string[]> => {
      const cached = clusterMembersCache.current.get(cid);
      if (cached) return cached;
      const existing = clusterMembersInflight.current.get(cid);
      if (existing) return existing;
      const promise = (async () => {
        try {
          const resp = await fetch(
            `/api/atlas/clusters/${cid}/members?projection=${encodeURIComponent(projection)}`,
          );
          if (!resp.ok) return [];
          const body = (await resp.json()) as { paper_ids: string[] };
          clusterMembersCache.current.set(cid, body.paper_ids);
          return body.paper_ids;
        } finally {
          clusterMembersInflight.current.delete(cid);
        }
      })();
      clusterMembersInflight.current.set(cid, promise);
      return promise;
    },
    [projection],
  );

  const handleLabelHoverEnter = useCallback(
    async (cid: number) => {
      hoveredClusterRef.current = cid;
      const memberIds = await fetchClusterMembers(cid);
      // Bail if the user has already moved on to another label before
      // our fetch landed — selection-thrash is annoying to look at.
      if (hoveredClusterRef.current !== cid) return;
      const scatter = scatterRef.current;
      if (!scatter) return;
      const idxs: number[] = [];
      for (const pid of memberIds) {
        const idx = indexByPaperId.get(pid);
        if (idx !== undefined) idxs.push(idx);
      }
      if (idxs.length > 0) {
        scatter.select(idxs, { preventEvent: true });
      }
    },
    [fetchClusterMembers, indexByPaperId],
  );

  const handleLabelHoverLeave = useCallback(() => {
    hoveredClusterRef.current = null;
    const scatter = scatterRef.current;
    if (!scatter) return;
    // Restore the search-selection. If there's no search-selection,
    // deselect entirely. We preventEvent so our own onSelect handler
    // doesn't fire and pin a paper from a cluster's member list.
    const want = selectedIndicesRef.current;
    if (want.length === 0) scatter.deselect({ preventEvent: true });
    else scatter.select(want, { preventEvent: true });
  }, []);

  // Click a label -> zoom the scatter camera to fill the viewport with
  // its bbox. After the zoom completes, the 'view' event fires
  // overlayTick, which triggers a re-fetch at the new (deeper) lambda.
  const handleLabelClick = useCallback(
    (bbox: [number, number, number, number]) => {
      const scatter = scatterRef.current;
      if (!scatter || !worldToNdc) return;
      // Convert PaCMAP-world bbox to NDC, padded slightly so the label
      // doesn't graze the canvas edge.
      const PADDING = 1.25;
      const cxw = (bbox[0] + bbox[2]) / 2;
      const cyw = (bbox[1] + bbox[3]) / 2;
      const halfW = ((bbox[2] - bbox[0]) / 2) * PADDING;
      const halfH = ((bbox[3] - bbox[1]) / 2) * PADDING;
      const cx = (cxw - worldToNdc.cx) * worldToNdc.scale;
      const cy = (cyw - worldToNdc.cy) * worldToNdc.scale;
      const w = Math.max(halfW * 2 * worldToNdc.scale, 0.02);
      const h = Math.max(halfH * 2 * worldToNdc.scale, 0.02);
      void scatter.zoomToArea(
        { x: cx - w / 2, y: cy - h / 2, width: w, height: h },
        { transition: true, transitionDuration: 600 },
      );
    },
    [worldToNdc],
  );

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

  // Apply the search multi-select to the live scatterplot. preventEvent
  // stops regl from firing back at our onSelect handler (which would
  // try to pin the selected points to the sidebar in a loop).
  useEffect(() => {
    const scatter = scatterRef.current;
    if (!scatter) return;
    if (selectedIndices.length === 0) {
      scatter.deselect({ preventEvent: true });
    } else {
      scatter.select(selectedIndices, { preventEvent: true });
    }
  }, [selectedIndices]);

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
              {points ? ` · ${points.length.toLocaleString()} papers` : ""}
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

          {/* Loading state */}
          {!points && !error && (
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

          {/* Search-selected markers: yellow ring overlays sitting on
              top of the canvas so chosen papers stand out even against
              dense same-coloured neighbours. Pointer-events disabled
              so they don't intercept the scatter's pan/zoom/click. */}
          {overlayPositions.map((p) => (
            <div
              key={p.paperId}
              className="pointer-events-none absolute z-20"
              style={{
                left: p.x,
                top: p.y,
                width: 20,
                height: 20,
                transform: "translate(-50%, -50%)",
              }}
            >
              <div
                className="h-full w-full rounded-full border-2"
                style={{
                  borderColor: "#ffd84a",
                  boxShadow: "0 0 8px 2px rgba(255, 216, 74, 0.55)",
                }}
              />
            </div>
          ))}

          {/* Fractal cluster labels — HTML overlay synced to regl-
              scatterplot's camera via overlayTick. No collision
              detection: if labels overlap, the user zooms in (or
              dials down the density slider). The control panel below
              lets them tune the label-count knob. */}
          {projectedLabels.map((l) => {
            // Font size + opacity scale with paper_count per the plan.
            // We additionally damp opacity when many labels are visible
            // so a dense viewport reads more like a tag cloud than a
            // wall of text.
            const pc = Math.max(1, l.paper_count);
            const fontSize = Math.min(28, Math.max(10, 12 + 2 * Math.log10(pc)));
            // 100% opacity per user request — easier to read on the
            // dark canvas. We still scale font-size with paper_count so
            // visually-dominant clusters get bigger labels.
            const opacity = 1;
            return (
              <button
                key={l.cluster_id}
                type="button"
                onClick={() => handleLabelClick(l.bbox)}
                onMouseEnter={() => handleLabelHoverEnter(l.cluster_id)}
                onMouseLeave={handleLabelHoverLeave}
                title={`${l.paper_count.toLocaleString()} papers`}
                className="absolute z-10 select-none whitespace-nowrap font-medium text-white/90 hover:text-white hover:underline focus:outline-none transition-colors"
                style={{
                  left: l.x,
                  top: l.y,
                  transform: "translate(-50%, -50%)",
                  fontSize: `${fontSize}px`,
                  opacity,
                  textShadow:
                    "0 0 4px rgba(0,0,0,0.95), 0 0 8px rgba(0,0,0,0.8), 0 1px 2px rgba(0,0,0,0.9)",
                  // Tag the DOM so headless-Chrome verification can
                  // confirm we rendered something. The visual screenshot
                  // is the ground truth but a data-attr helps when the
                  // canvas behind is also white-ish (it isn't, but still).
                }}
                data-cluster-id={l.cluster_id}
                data-cluster-label
              >
                {l.label}
              </button>
            );
          })}

          {/* Control panel — collapsible, pinned to bottom-right. v1
              holds a single label-density knob. Future controls (max
              paper age, embedding-distance threshold, etc.) anchor
              here. The header chevron toggles open/closed; the panel
              persists open/closed and slider value to localStorage. */}
          <div className="absolute bottom-3 right-3 z-20 select-none">
            <div className="card bg-base-200/85 backdrop-blur border border-base-300/60 text-xs shadow-lg overflow-hidden min-w-[220px]">
              <button
                type="button"
                onClick={() => setControlPanelOpen((v) => !v)}
                className="w-full flex items-center justify-between gap-3 px-3 py-2 hover:bg-base-300/30"
                aria-expanded={controlPanelOpen}
                title={controlPanelOpen ? "Collapse" : "Expand"}
                data-control-panel-toggle
              >
                <span className="text-base-content/60 font-semibold uppercase tracking-wider text-[10px]">
                  Controls
                </span>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className={`h-3 w-3 text-base-content/40 transition-transform ${controlPanelOpen ? "rotate-180" : ""}`}
                >
                  <path
                    fillRule="evenodd"
                    d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
              {controlPanelOpen && (
                <div className="px-3 pb-3 pt-1 space-y-2">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label
                        htmlFor="atlas-label-density"
                        className="text-base-content/70"
                      >
                        Label density
                      </label>
                      <span className="text-base-content/50 font-mono tabular-nums text-[11px]">
                        {targetCount}
                      </span>
                    </div>
                    <input
                      id="atlas-label-density"
                      type="range"
                      min={MIN_TARGET_COUNT}
                      max={MAX_TARGET_COUNT}
                      step={1}
                      value={targetCount}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10);
                        if (!Number.isNaN(v)) setTargetCount(v);
                      }}
                      className="w-full range range-xs"
                      data-control-target-count
                    />
                    <div className="flex justify-between text-[10px] text-base-content/40 mt-0.5">
                      <span>{MIN_TARGET_COUNT}</span>
                      <span>{MAX_TARGET_COUNT}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

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
