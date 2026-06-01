import Head from "next/head";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  streamAtlas,
  type AtlasPoint,
  type AtlasHeader,
} from "../lib/streamAtlas";
import {
  hexToRgba,
  FALLBACK_RGBA,
  type DeckAtlasCanvasProps,
} from "../components/DeckAtlasCanvas";

// DeckAtlasCanvas pulls in WebGL at import time, so it has to be loaded
// browser-only. next/dynamic with ssr:false is the path of least
// resistance — the page itself renders happily on the server, the canvas
// hot-swaps in on the client.
const DeckAtlasCanvas = dynamic<DeckAtlasCanvasProps>(
  () =>
    import("../components/DeckAtlasCanvas").then(
      (m) => m.default,
    ),
  { ssr: false, loading: () => null },
);

// ---------------------------------------------------------------------------
// API contract.
// ---------------------------------------------------------------------------

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
): { legend: { source: string; color: string }[] } {
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
  return { legend };
}

export default function AtlasPage() {
  // Initial projection: ?projection=<name> wins over the default. We
  // read from window.location so it works without router.isReady wait.
  const [projection] = useState<string>(() => {
    if (typeof window === "undefined") return DEFAULT_PROJECTION;
    const sp = new URLSearchParams(window.location.search);
    return sp.get("projection")?.trim() || DEFAULT_PROJECTION;
  });
  // points grows batch-by-batch as the NDJSON stream lands; we use
  // `header === null` as the loading sentinel since `points` legitimately
  // starts empty and isn't a useful loaded-yet flag.
  const [points, setPoints] = useState<AtlasPoint[]>([]);
  const [header, setHeader] = useState<AtlasHeader | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Sources that the user has clicked off in the legend. Empty Set =
  // show everything. arxiv used to be hidden by default because at the
  // full-corpus scale its discrete dot cloud washed out the conference
  // clusters. With the deck.gl renderer arxiv is now rendered as a hex
  // density backdrop (matplotlib-style topology) rather than dots, so
  // showing it by default gives the corpus its expected "land masses"
  // look on first paint. Users can still toggle it off from the legend.
  const [hiddenSources, setHiddenSources] = useState<Set<string>>(
    () => new Set(),
  );
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Hovered paper + screen-space position for the floating tooltip. The
  // canvas delivers both via its onHover callback so we don't need a
  // separate mousemove listener on the container.
  const [hovered, setHovered] = useState<{
    point: AtlasPoint;
    screen: { x: number; y: number };
  } | null>(null);

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
  // Sidebar collapse state. Default starts expanded so SSR + first client
  // render agree (server has no window.matchMedia). The mobile check
  // runs after mount and flips us to collapsed if the viewport is narrow
  // — there's a one-frame flash of the open sidebar on mobile, which is
  // acceptable. We don't re-react to subsequent resize because flipping
  // the panel under the user while they drag the window is annoying.
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  useEffect(() => {
    if (window.matchMedia("(max-width: 768px)").matches) {
      setSidebarCollapsed(true);
    }
  }, []);

  // Search bar state.
  // - `searchInput` mirrors the input field.
  // - `searchResults` is the dropdown list, fetched (debounced) from
  //   /api/search. Each entry is filtered down to papers that actually
  //   appear in the current atlas — we can't highlight a point that
  //   isn't on the map.
  // - `selectedIds` is the multi-select set of papers the user has
  //   ticked; those points get the yellow-halo highlight on the canvas.
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
  // "Hide all" — derives the full source set from the current points
  // list and adds every one to hiddenSources. If everything ends up
  // hidden the canvas goes blank; that's fine and reversible, the user
  // can click any legend entry to restore it.
  const hideAllSources = useCallback(() => {
    const all = new Set<string>();
    for (const p of points) all.add(p.source ?? "unknown");
    setHiddenSources(all);
  }, [points]);

  // Fetch points on mount via NDJSON streaming. A fresh AbortController
  // per effect run so projection changes / unmount cancel the in-flight
  // fetch cleanly (the underlying ReadableStream propagates abort).
  useEffect(() => {
    const ctrl = new AbortController();
    // Reset header + points on (re)entry — a projection change must not
    // show stale geometry from the previous projection while the new
    // stream is in flight.
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
          (batch) => setPoints((prev) => prev.concat(batch)),
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
  }, [projection]);

  // Map paper_id → atlas index, used by the search dropdown to filter
  // out papers that aren't in the current projection (we can't highlight
  // them on this map).
  const indexByPaperId = useMemo(() => {
    const m = new Map<string, number>();
    for (let i = 0; i < points.length; i++) m.set(points[i].paper_id, i);
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

  const { legend } = useMemo(
    () => buildSourceColorIndex(points),
    [points],
  );

  // Source name → RGBA tuple, the form deck.gl's accessors expect.
  // Memoised so DeckAtlasCanvas's updateTriggers see a stable reference
  // and don't thrash buffer uploads on every render.
  const sourceColorMap = useMemo(() => {
    const m = new Map<string, [number, number, number, number]>();
    for (const { source, color } of legend) {
      m.set(source, hexToRgba(color));
    }
    return m;
  }, [legend]);

  const sourceToColor = useCallback(
    (source: string | null): [number, number, number, number] =>
      sourceColorMap.get(source ?? "unknown") ?? FALLBACK_RGBA,
    [sourceColorMap],
  );

  // Hover/click pass through from the canvas. The canvas resolves the
  // nearest paper in a hex cell for arxiv picks; we just receive the
  // paper object and screen position and wire them to the existing
  // tooltip + sidebar state.
  const handleHover = useCallback(
    (
      paper: AtlasPoint | null,
      screen: { x: number; y: number } | null,
    ) => {
      if (paper && screen) {
        setHovered({ point: paper, screen });
        setHoverPaperId(paper.paper_id);
        void fetchPaperDetail(paper.paper_id);
      } else {
        setHovered(null);
      }
    },
    [fetchPaperDetail],
  );

  const handleClick = useCallback(
    (paper: AtlasPoint) => {
      setPinnedPaperId(paper.paper_id);
      void fetchPaperDetail(paper.paper_id);
    },
    [fetchPaperDetail],
  );

  // bbox for the canvas — taken straight from the stream header so the
  // camera fits the full corpus on first paint, even before all batches
  // have arrived.
  const bbox: [number, number, number, number] | null = header?.bbox ?? null;

  // If the hovered point's source is in hiddenSources, suppress the
  // tooltip. Can happen if the user hides a source while the cursor
  // is still parked on a venue dot of that source — the dot disappears
  // visually but our `hovered` state would otherwise linger.
  const hoverSuppressed =
    hovered && hiddenSources.has(hovered.point.source ?? "unknown");

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
              {` · ${points.length.toLocaleString()} / ${
                header ? header.total.toLocaleString() : "?"
              } papers`}
            </span>
            {/* Collapse / expand the details sidebar. Default-collapsed
                on mobile so the canvas keeps its real estate; users can
                still bring it back with one tap. */}
            <button
              type="button"
              onClick={() => setSidebarCollapsed((prev) => !prev)}
              title={sidebarCollapsed ? "Show paper details" : "Hide paper details"}
              className="ml-auto btn btn-ghost btn-sm text-base-content/60 hover:text-base-content"
            >
              {sidebarCollapsed ? "Details ›" : "‹ Hide details"}
            </button>
            <a
              href="/graph"
              className="btn btn-ghost btn-sm text-base-content/60 hover:text-base-content"
            >
              Graph view
            </a>
          </div>
        </header>

        {/* Body: canvas (full-width when collapsed, otherwise paired
            with a 360px paper details sidebar). */}
        <div
          className={`grid min-h-0 ${
            sidebarCollapsed ? "grid-cols-[1fr]" : "grid-cols-[1fr,360px]"
          }`}
        >
          <div ref={containerRef} className="relative min-h-0 w-full">
            {/* The canvas component manages its own GL context + layers.
                We pass it raw points + filter/selection sets; it builds
                the HexagonLayer (arxiv) + ScatterplotLayer (venues) +
                ScatterplotLayer (highlights) composition. */}
            <DeckAtlasCanvas
              points={points}
              bbox={bbox}
              hiddenSources={hiddenSources}
              selectedIds={selectedIds}
              sourceToColor={sourceToColor}
              onHover={handleHover}
              onClick={handleClick}
            />

            {/* Loading state — points starts as [] (truthy) so the
                equivalent "nothing useful yet" sentinel is the header
                not having arrived. */}
            {!header && !error && (
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
                canvas via the IconLayer-style scatter layer the canvas
                renders for `selectedIds`. */}
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
                            hidden ? `Show ${l.source}` : `Hide ${l.source}`
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

            {/* Hover tooltip — anchored to the cursor (screen position
                from deck.gl's picking info). */}
            {hovered && !hoverSuppressed && (
              <div
                className="pointer-events-none absolute z-30 max-w-sm card bg-base-200/95 backdrop-blur border border-base-300/60 p-2 text-xs shadow-lg"
                style={{
                  left: Math.min(
                    hovered.screen.x + 12,
                    (containerRef.current?.clientWidth ?? 0) - 320,
                  ),
                  top: Math.min(
                    hovered.screen.y + 12,
                    (containerRef.current?.clientHeight ?? 0) - 80,
                  ),
                }}
              >
                <div className="font-semibold leading-snug">
                  {hovered.point.title}
                </div>
                <div className="text-base-content/60 mt-1">
                  {hovered.point.source || "unknown source"} ·{" "}
                  {hovered.point.paper_id}
                </div>
              </div>
            )}

            {/* Hint — pushed to bottom-right because the canvas owns
                bottom-left now (the tuning button lives there). */}
            <div className="absolute bottom-3 right-3 text-[10px] text-base-content/40 pointer-events-none text-right max-w-[60%]">
              Scroll to zoom · drag to pan · click a point to pin it to the
              sidebar
            </div>
          </div>

          {/* Right sidebar — full paper details for the most recently
              hovered (or sidebar-pinned via search) paper. Mirrors the
              graph page's HoverPreview so the two pages feel consistent.
              Hidden entirely when sidebarCollapsed; the header button
              brings it back. */}
          {!sidebarCollapsed && <AtlasSidebar
            paper={
              sidebarPaperId
                ? paperCache[sidebarPaperId] ?? {
                    paper_id: sidebarPaperId,
                    title:
                      points.find((p) => p.paper_id === sidebarPaperId)
                        ?.title ?? sidebarPaperId,
                    source:
                      points.find((p) => p.paper_id === sidebarPaperId)
                        ?.source ?? null,
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
          />}
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
