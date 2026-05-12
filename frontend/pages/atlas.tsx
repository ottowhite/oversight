import Head from "next/head";
import { useRouter } from "next/router";
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
  const router = useRouter();
  const [projection] = useState<string>(DEFAULT_PROJECTION);
  const [points, setPoints] = useState<AtlasPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const scatterRef = useRef<ScatterplotApi | null>(null);
  // Keep the points list in a ref so event callbacks (registered once)
  // can look up paper_ids without re-subscribing on every render.
  const pointsRef = useRef<AtlasPoint[] | null>(null);
  pointsRef.current = points;

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
      const rect = containerRef.current!.getBoundingClientRect();
      const colors = legend.map((l) => l.color);
      scatter = createScatterplot({
        canvas: canvasRef.current,
        width: rect.width,
        height: rect.height,
        // Source category lives in points[i][2]; tell the renderer to
        // colour by it and provide one colour per category index.
        pointColor: colors.length > 0 ? colors : [FALLBACK_COLOR],
        pointColorActive: "#ffffff",
        pointColorHover: "#ffffff",
        pointSize: 2.5,
        opacity: 0.7,
        backgroundColor: [0, 0, 0, 1],
      });
      scatterRef.current = scatter;
      await scatter.draw(normalized);

      const onOver = (idx: unknown) => {
        if (typeof idx === "number") setHoverIdx(idx);
      };
      const onOut = () => setHoverIdx(null);
      const onSelect = (payload: unknown) => {
        const pts = (payload as { points?: number[] } | undefined)?.points;
        if (!pts || pts.length === 0) return;
        const idx = pts[0];
        const list = pointsRef.current;
        if (!list || idx < 0 || idx >= list.length) return;
        const paperId = list[idx].paper_id;
        // Navigate to the existing /graph page so a click on the
        // atlas immediately opens the similarity-graph view for
        // that paper's neighborhood.
        router.push(`/graph?papers=${encodeURIComponent(paperId)}`);
      };
      scatter.subscribe("pointOver", onOver);
      scatter.subscribe("pointOut", onOut);
      scatter.subscribe("select", onSelect);
    })().catch((err) => {
      console.error("[atlas] failed to init scatterplot", err);
      setError(String(err));
    });

    // Resize: when the container changes size, push the new dims into
    // the scatter. ResizeObserver fires on first hookup as well, so
    // this also handles the initial layout cleanly.
    const ro = new ResizeObserver((entries) => {
      if (!scatter) return;
      const entry = entries[0];
      if (!entry) return;
      const w = entry.contentRect.width;
      const h = entry.contentRect.height;
      scatter.set({ width: w, height: h });
    });
    ro.observe(containerRef.current!);

    return () => {
      cancelled = true;
      ro.disconnect();
      if (scatter) scatter.destroy();
      scatterRef.current = null;
    };
  }, [normalized, legend, router]);

  const hovered = hoverIdx !== null && points ? points[hoverIdx] : null;

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

          {/* Legend */}
          {legend.length > 0 && (
            <div className="absolute top-3 right-3 card bg-base-200/80 backdrop-blur border border-base-300/60 p-2 text-xs">
              <div className="text-base-content/60 mb-1 font-semibold">
                Source
              </div>
              <ul className="space-y-0.5">
                {legend.map((l) => (
                  <li key={l.source} className="flex items-center gap-2">
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: l.color }}
                    />
                    <span className="text-base-content/80">{l.source}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Hover tooltip — anchored to mouse, follows the cursor */}
          {hovered && mousePos && (
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
            Scroll to zoom · drag to pan · click a point to open the graph
            view
          </div>
        </div>
      </main>
    </>
  );
}
