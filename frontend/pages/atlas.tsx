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

// Default projection: matches the 18k-PL load. Will be flipped to
// "pacmap_v1" once the sibling agent's full-corpus CSV is loaded.
const DEFAULT_PROJECTION = "pacmap_pl_v1";

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

  const { byIndex: categoryByIndex, legend } = useMemo(
    () => (points ? buildSourceColorIndex(points) : { byIndex: [], legend: [] }),
    [points],
  );

  const normalized = useMemo(
    () => (points ? normalizePoints(points, categoryByIndex) : []),
    [points, categoryByIndex],
  );

  // Recompute the indices regl-scatterplot should keep visible. We use
  // scatter.filter([idx, ...]) rather than re-drawing with a subset
  // because filter() preserves the original indices — that means the
  // click handler can still look up paper_id via pointsRef.current[idx]
  // without remapping.
  const visibleIndices = useMemo(() => {
    if (!points) return [] as number[];
    if (hiddenSources.size === 0) return [] as number[];
    const out: number[] = [];
    for (let i = 0; i < points.length; i++) {
      if (!hiddenSources.has(points[i].source ?? "unknown")) out.push(i);
    }
    return out;
  }, [points, hiddenSources]);

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
        pointColorActive: "#ffffff",
        pointColorHover: "#ffffff",
        pointSize: 3,
        opacity: 0.7,
        backgroundColor: [0, 0, 0, 1],
      });
      scatterRef.current = scatter;
      await scatter.draw(normalized);
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
