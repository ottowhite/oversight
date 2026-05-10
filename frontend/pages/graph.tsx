import Head from "next/head";
import dynamic from "next/dynamic";
import { useRouter } from "next/router";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";

// react-force-graph-2d touches `window` at import time, so it must be
// loaded only on the client. Disable SSR via next/dynamic.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
}) as any;

// ---------------------------------------------------------------------------
// API contract types — must match docs/similarity-graph-plan.md exactly.
// When Phase 2 swaps in the real backend, these types are reused as-is.
// ---------------------------------------------------------------------------

type Paper = {
  paper_id: string;
  title: string;
  authors: string[];
};

type NeighborApiEntry = Paper & { similarity: number };

type NeighborsResponse = {
  seed: Paper;
  neighbors: NeighborApiEntry[];
};

type SimilarityDistribution = {
  p50: number;
  p90: number;
  p95: number;
  p99: number;
  p99_5: number;
  p99_9: number;
};

// ---------------------------------------------------------------------------
// Local state shape (copied verbatim from the plan).
// ---------------------------------------------------------------------------

type Mode = "topk" | "threshold" | "mutual_knn";

type Neighbor = { paper_id: string; similarity: number };

type NodeCache = {
  paper_id: string;
  topN: Neighbor[];
  mutualN?: Neighbor[];
};

type GraphEdge = { source: string; target: string; similarity: number };

type GraphState = {
  nodes: Paper[];
  edges: GraphEdge[];
  mode: Mode;
  k: number;
  threshold: number;
  cache: Record<string, NodeCache>;
};

// ---------------------------------------------------------------------------
// API fetchers.
//
// Phase 2: real /api/papers/<id>/neighbors is wired in. The corpus
// similarity-distribution endpoint (Phase 1B) is not yet implemented on
// the backend, so fetchDistribution falls back to FALLBACK_DISTRIBUTION
// — hard-coded percentiles that are roughly representative of our
// embedding model. The threshold slider remains usable in the meantime.
// ---------------------------------------------------------------------------

// Sensible defaults for gemini-embedding-001 abstract cosines, used until
// /api/embeddings/similarity_distribution exists. Replace by deleting the
// fallback branch once Phase 1B ships.
const FALLBACK_DISTRIBUTION: SimilarityDistribution = {
  p50: 0.42,
  p90: 0.58,
  p95: 0.62,
  p99: 0.71,
  p99_5: 0.74,
  p99_9: 0.79,
};

async function fetchNeighbors(
  paperId: string,
  opts: { k: number; mutual: boolean },
): Promise<NeighborsResponse> {
  const params = new URLSearchParams({
    k: String(opts.k),
    mutual: opts.mutual ? "true" : "false",
  });
  const resp = await fetch(
    `/api/papers/${encodeURIComponent(paperId)}/neighbors?${params}`,
  );
  if (!resp.ok) {
    let detail = "";
    try {
      const body = await resp.json();
      if (body && typeof body.error === "string") detail = `: ${body.error}`;
    } catch {
      /* response was not JSON */
    }
    throw new Error(`neighbors fetch failed (${resp.status})${detail}`);
  }
  return (await resp.json()) as NeighborsResponse;
}

// Module-level cache for the distribution fetch. Memoizing here (rather
// than per-component) means React StrictMode double-mounting and Fast
// Refresh remounts don't re-fire the request. The browser unconditionally
// logs failed fetches as "Failed to load resource" — there's no JS API
// to silence that — so the next-best thing is to only ever issue one
// request per session.
let distributionCache: Promise<SimilarityDistribution> | null = null;

async function fetchDistribution(): Promise<SimilarityDistribution> {
  if (distributionCache) return distributionCache;
  // TODO Phase 1B: drop the try/fallback once
  // /api/embeddings/similarity_distribution exists.
  distributionCache = (async () => {
    try {
      const resp = await fetch(`/api/embeddings/similarity_distribution`);
      if (resp.ok) return (await resp.json()) as SimilarityDistribution;
      // Expected today: Phase 1B endpoint not implemented yet. Don't
      // promote to console.error — the threshold slider degrades
      // gracefully via FALLBACK_DISTRIBUTION.
      console.debug(
        `[graph] /api/embeddings/similarity_distribution returned ` +
          `${resp.status}; using FALLBACK_DISTRIBUTION until Phase 1B lands`,
      );
    } catch (err) {
      console.debug(
        `[graph] /api/embeddings/similarity_distribution unreachable ` +
          `(${err}); using FALLBACK_DISTRIBUTION`,
      );
    }
    return FALLBACK_DISTRIBUTION;
  })();
  return distributionCache;
}

// ---------------------------------------------------------------------------
// Edge derivation: pure function from cache + mode + slider value.
// All slider drags in topk/threshold/mutual_knn (after the mutual fetch is
// cached) flow through this — no network involvement.
// ---------------------------------------------------------------------------

const NEIGHBOR_CEILING = 20;

function deriveEdges(
  cache: Record<string, NodeCache>,
  mode: Mode,
  k: number,
  threshold: number,
): GraphEdge[] {
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  for (const entry of Object.values(cache)) {
    const list =
      mode === "mutual_knn"
        ? entry.mutualN ?? []
        : entry.topN;
    let selected: Neighbor[];
    if (mode === "topk" || mode === "mutual_knn") {
      selected = list.slice(0, k);
    } else {
      selected = list.filter((n) => n.similarity >= threshold);
    }
    for (const n of selected) {
      // Dedupe undirected edges so we don't double-render A↔B when both
      // endpoints are in the cache.
      const key =
        entry.paper_id < n.paper_id
          ? `${entry.paper_id}|${n.paper_id}`
          : `${n.paper_id}|${entry.paper_id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      edges.push({
        source: entry.paper_id,
        target: n.paper_id,
        similarity: n.similarity,
      });
    }
  }
  return edges;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const DEFAULT_K = 15;
const DEFAULT_K_MAX = 15;

const MODE_LABEL: Record<Mode, string> = {
  topk: "top-k",
  threshold: "threshold",
  mutual_knn: "mutual-kNN",
};

export default function GraphPage() {
  const router = useRouter();
  // router.query is empty until router.isReady on first client render.
  // Wait for it before triggering any fetches so we don't hit the API
  // with an empty seed.
  const seedId = useMemo<string | null>(() => {
    if (!router.isReady) return null;
    const raw = router.query.seed;
    if (typeof raw === "string" && raw.length > 0) return raw;
    if (Array.isArray(raw) && raw.length > 0) return raw[0];
    return null;
  }, [router.isReady, router.query.seed]);

  const [graph, setGraph] = useState<GraphState>({
    nodes: [],
    edges: [],
    mode: "topk",
    k: DEFAULT_K,
    threshold: 0,
    cache: {},
  });
  const [distribution, setDistribution] = useState<SimilarityDistribution | null>(null);
  const [hoverNode, setHoverNode] = useState<Paper | null>(null);
  const [loadingNodeId, setLoadingNodeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Force-graph imperative handle for fit-to-view / reheat.
  const fgRef = useRef<any>(null);
  // Track container size so the canvas fills its parent.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 800, h: 600 });

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const update = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    update();
    const obs = new ResizeObserver(update);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // -------------------------------------------------------------------------
  // Bootstrap: fetch the corpus distribution + seed neighbors on mount.
  // -------------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    fetchDistribution()
      .then((d) => {
        if (cancelled) return;
        setDistribution(d);
        // Anchor the threshold slider at the 99th percentile by default.
        setGraph((g) => (g.threshold === 0 ? { ...g, threshold: d.p99 } : g));
      })
      .catch((err) => !cancelled && setError(String(err)));
    return () => {
      cancelled = true;
    };
  }, []);

  // Expand a node: fetch its top-N (and mutual-N if needed), merge into
  // cache + nodes, then re-derive edges. First click of a node hits the
  // network; subsequent clicks are no-ops (cache hit).
  const expandNode = useCallback(
    async (paperId: string, modeAtClick: Mode) => {
      setError(null);
      const needMutual = modeAtClick === "mutual_knn";
      const existing = graph.cache[paperId];
      const haveTop = !!existing;
      const haveMutual = !!existing?.mutualN;
      if (haveTop && (!needMutual || haveMutual)) return;

      setLoadingNodeId(paperId);
      try {
        const tasks: Array<Promise<NeighborsResponse>> = [];
        if (!haveTop) {
          tasks.push(fetchNeighbors(paperId, { k: NEIGHBOR_CEILING, mutual: false }));
        }
        if (needMutual && !haveMutual) {
          tasks.push(fetchNeighbors(paperId, { k: NEIGHBOR_CEILING, mutual: true }));
        }
        const responses = await Promise.all(tasks);

        setGraph((g) => {
          const cache = { ...g.cache };
          const prevEntry = cache[paperId] ?? { paper_id: paperId, topN: [] };
          let nextEntry: NodeCache = { ...prevEntry };
          const newPapers: Paper[] = [];

          // Walk responses in the same order as `tasks`.
          let idx = 0;
          if (!haveTop) {
            const r = responses[idx++];
            nextEntry.topN = r.neighbors.map((n) => ({
              paper_id: n.paper_id,
              similarity: n.similarity,
            }));
            // Make sure the seed itself is in the node set with rich metadata.
            newPapers.push(r.seed);
            for (const n of r.neighbors) {
              newPapers.push({
                paper_id: n.paper_id,
                title: n.title,
                authors: n.authors,
              });
            }
          }
          if (needMutual && !haveMutual) {
            const r = responses[idx++];
            nextEntry.mutualN = r.neighbors.map((n) => ({
              paper_id: n.paper_id,
              similarity: n.similarity,
            }));
            // Mutual-kNN may surface papers we haven't seen in top-N.
            for (const n of r.neighbors) {
              newPapers.push({
                paper_id: n.paper_id,
                title: n.title,
                authors: n.authors,
              });
            }
          }
          cache[paperId] = nextEntry;

          // Merge newPapers into g.nodes (dedupe by paper_id).
          const knownIds = new Set(g.nodes.map((p) => p.paper_id));
          const merged = [...g.nodes];
          for (const p of newPapers) {
            if (knownIds.has(p.paper_id)) continue;
            knownIds.add(p.paper_id);
            merged.push(p);
          }

          const edges = deriveEdges(cache, g.mode, g.k, g.threshold);
          return { ...g, cache, nodes: merged, edges };
        });
      } catch (err) {
        setError(String(err));
      } finally {
        setLoadingNodeId(null);
      }
    },
    [graph.cache],
  );

  // Initial seed expansion. Re-runs if the user navigates to a new ?seed=.
  useEffect(() => {
    if (!seedId) return;
    expandNode(seedId, "topk");
    // We intentionally depend only on seedId — expandNode closes over the
    // current cache, but for the bootstrap call the cache is empty anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedId]);

  // -------------------------------------------------------------------------
  // Slider / mode handlers (pure cache-derived re-renders).
  // -------------------------------------------------------------------------

  const setMode = useCallback(
    async (mode: Mode) => {
      setGraph((g) => {
        const next: GraphState = {
          ...g,
          mode,
          k: mode === "threshold" ? g.k : g.k, // keep k as-is across topk/mutual switches
          threshold:
            mode === "threshold" && g.threshold === 0 && distribution
              ? distribution.p99
              : g.threshold,
        };
        next.edges = deriveEdges(next.cache, next.mode, next.k, next.threshold);
        return next;
      });
      // If we just entered mutual-kNN and the seed has no cached mutual
      // results yet, fetch them. (Other already-expanded nodes stay
      // un-fetched in mutual mode until clicked — matches the plan's
      // "first switch into mutual-kNN for a node already in the graph"
      // wording.)
      if (mode === "mutual_knn" && seedId) {
        const entry = graph.cache[seedId];
        if (entry && !entry.mutualN) {
          await expandNode(seedId, "mutual_knn");
        }
      }
    },
    [distribution, graph.cache, seedId, expandNode],
  );

  const setK = useCallback((k: number) => {
    setGraph((g) => ({ ...g, k, edges: deriveEdges(g.cache, g.mode, k, g.threshold) }));
  }, []);

  const setThreshold = useCallback((t: number) => {
    setGraph((g) => ({
      ...g,
      threshold: t,
      edges: deriveEdges(g.cache, g.mode, g.k, t),
    }));
  }, []);

  // -------------------------------------------------------------------------
  // Derived graph data for ForceGraph2D.
  // -------------------------------------------------------------------------

  const fgData = useMemo(() => {
    // Hide nodes that have no edges in the current derived view, otherwise
    // top-k with k<20 (or threshold mode) leaves orphan nodes floating
    // disconnected. The cache still holds them, so they reappear instantly
    // when the slider widens — no re-fetch needed.
    //
    // The seed always renders even if every edge filtered out, so the
    // user can always see "where they are" in the graph.
    const connected = new Set<string>();
    if (seedId) connected.add(seedId);
    for (const e of graph.edges) {
      connected.add(typeof e.source === "string" ? e.source : String(e.source));
      connected.add(typeof e.target === "string" ? e.target : String(e.target));
    }
    const nodes = graph.nodes
      .filter((p) => connected.has(p.paper_id))
      .map((p) => ({ id: p.paper_id, paper: p }));
    const links = graph.edges.map((e) => ({
      source: e.source,
      target: e.target,
      similarity: e.similarity,
    }));
    return { nodes, links };
  }, [graph.nodes, graph.edges, seedId]);

  // Per-node degree, for sizing.
  const degreeById = useMemo(() => {
    const d: Record<string, number> = {};
    for (const e of graph.edges) {
      d[e.source] = (d[e.source] ?? 0) + 1;
      d[e.target] = (d[e.target] ?? 0) + 1;
    }
    return d;
  }, [graph.edges]);

  // Similarity-of-each-neighbor-to-the-seed, for the hover tooltip.
  const simToSeed = useMemo(() => {
    if (!seedId) return {} as Record<string, number>;
    const seedCache = graph.cache[seedId];
    if (!seedCache) return {} as Record<string, number>;
    const m: Record<string, number> = { [seedId]: 1.0 };
    for (const n of seedCache.topN) m[n.paper_id] = n.similarity;
    return m;
  }, [graph.cache, seedId]);

  // Look up the seed paper's title for the header. The /neighbors response
  // includes the seed's metadata in `response.seed`, which expandNode
  // merges into graph.nodes — no separate paper-metadata fetch required.
  const seedTitle = useMemo(() => {
    if (!seedId) return null;
    const p = graph.nodes.find((n) => n.paper_id === seedId);
    return p?.title ?? null;
  }, [graph.nodes, seedId]);

  // Force-graph spring-strength polish: more similar = stronger spring =
  // shorter rest length. We reach into the d3-force "link" force via the
  // imperative API exposed by react-force-graph-2d. When loaded through
  // next/dynamic the ref isn't always forwarded to the inner component
  // (Next 12 quirk), so guard everything and silently skip if the
  // imperative methods aren't reachable — visual encoding via
  // linkColor/linkWidth still communicates similarity to the user.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || typeof fg.d3Force !== "function") return;
    const linkForce = fg.d3Force("link");
    if (!linkForce || typeof linkForce.distance !== "function") return;
    linkForce.distance((link: any) => {
      // Map similarity 0.30..0.85 → distance 200..40.
      const s = typeof link.similarity === "number" ? link.similarity : 0.5;
      const norm = Math.max(0, Math.min(1, (s - 0.3) / 0.55));
      return 200 - norm * 160;
    });
    if (typeof linkForce.strength === "function") {
      linkForce.strength((link: any) => {
        const s = typeof link.similarity === "number" ? link.similarity : 0.5;
        return Math.max(0.05, Math.min(1, (s - 0.2) * 1.5));
      });
    }
    if (typeof fg.d3ReheatSimulation === "function") {
      fg.d3ReheatSimulation();
    }
  }, [fgData]);

  // -------------------------------------------------------------------------
  // Visual helpers.
  // -------------------------------------------------------------------------

  const linkColor = useCallback((link: any) => {
    const s = typeof link.similarity === "number" ? link.similarity : 0.5;
    const norm = Math.max(0, Math.min(1, (s - 0.3) / 0.55));
    // Vercel blue (#0070f3 = 0,112,243) at variable opacity.
    const alpha = (0.15 + norm * 0.7).toFixed(3);
    return `rgba(0, 112, 243, ${alpha})`;
  }, []);

  const linkWidth = useCallback((link: any) => {
    const s = typeof link.similarity === "number" ? link.similarity : 0.5;
    const norm = Math.max(0, Math.min(1, (s - 0.3) / 0.55));
    return 0.6 + norm * 2.2;
  }, []);

  const nodeVal = useCallback(
    (node: any) => {
      const deg = degreeById[node.id] ?? 0;
      // Seed node always reads as a hub.
      const base = node.id === seedId ? 6 : 2;
      return base + Math.sqrt(deg);
    },
    [degreeById, seedId],
  );

  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isSeed = node.id === seedId;
      const isLoading = loadingNodeId === node.id;
      const r = (nodeVal(node) + 1) / Math.max(globalScale, 0.5) * Math.min(globalScale, 1.6);
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
      ctx.fillStyle = isSeed ? "#ffffff" : "#0070f3";
      ctx.fill();
      if (isLoading) {
        ctx.strokeStyle = "#f5a623";
        ctx.lineWidth = 1.5 / globalScale;
        ctx.stroke();
      } else {
        ctx.strokeStyle = "rgba(255,255,255,0.4)";
        ctx.lineWidth = 0.8 / globalScale;
        ctx.stroke();
      }
    },
    [seedId, loadingNodeId, nodeVal],
  );

  // -------------------------------------------------------------------------
  // Slider configuration (mode-dependent).
  // -------------------------------------------------------------------------

  const slider = useMemo(() => {
    if (graph.mode === "topk") {
      return {
        label: "k (nearest neighbors per node)",
        valueLabel: String(graph.k),
        min: 1,
        max: NEIGHBOR_CEILING,
        step: 1,
        value: graph.k,
        onChange: (v: number) => setK(Math.round(v)),
        helper: `1–${NEIGHBOR_CEILING}, capped by the over-fetch ceiling`,
      };
    }
    if (graph.mode === "mutual_knn") {
      return {
        label: "k_max (mutual neighbors per node)",
        valueLabel: String(graph.k),
        min: 1,
        max: NEIGHBOR_CEILING,
        step: 1,
        value: graph.k,
        onChange: (v: number) => setK(Math.round(v)),
        helper: `1–${NEIGHBOR_CEILING}, mutual-kNN is a strict subset of top-k`,
      };
    }
    // threshold mode
    const dist = distribution;
    // Take the union of the corpus percentile envelope and the actual
    // cached similarities. The corpus envelope alone (p50–p99.9) is
    // calibrated to a random pair, but real neighborhoods often cluster
    // way above p99.9 (e.g. abstract-similar papers can sit at 0.85+
    // while p99.9 ≈ 0.79). Without expanding the slider, dragging
    // "all the way right" still leaves every edge in.
    const cachedSims: number[] = [];
    for (const entry of Object.values(graph.cache)) {
      for (const n of entry.topN) cachedSims.push(n.similarity);
      if (entry.mutualN) for (const n of entry.mutualN) cachedSims.push(n.similarity);
    }
    const obsMin = cachedSims.length > 0 ? Math.min(...cachedSims) : 0;
    const obsMax = cachedSims.length > 0 ? Math.max(...cachedSims) : 1;
    const baseMin = dist ? Math.max(0, dist.p50 - 0.05) : 0.3;
    const baseMax = dist ? Math.min(1, dist.p99_9 + 0.05) : 0.85;
    const min = Math.max(0, Math.min(baseMin, obsMin - 0.005));
    // +0.005 so the user can drag past the largest cached similarity and
    // see "0 edges," which is the only way to confirm the filter works.
    const max = Math.min(1, Math.max(baseMax, obsMax + 0.005));
    return {
      label: "T (cosine similarity threshold)",
      valueLabel: graph.threshold.toFixed(3),
      min,
      max,
      step: 0.001,
      value: graph.threshold,
      onChange: (v: number) => setThreshold(v),
      helper: dist ? percentileLabel(graph.threshold, dist) : "loading corpus distribution…",
    };
  }, [
    graph.mode,
    graph.k,
    graph.threshold,
    graph.cache,
    distribution,
    setK,
    setThreshold,
  ]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <>
      <Head>
        <title>Graph · Oversight</title>
      </Head>
      <main className="grid h-screen grid-rows-[auto,1fr]">
        <header className="border-b border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40">
          <div className="flex items-center gap-3 px-4 py-3">
            <a
              href="/"
              className="btn btn-ghost btn-sm btn-circle"
              title="Back to search"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path fillRule="evenodd" d="M9.78 4.22a.75.75 0 010 1.06L6.06 9h11.69a.75.75 0 010 1.5H6.06l3.72 3.72a.75.75 0 11-1.06 1.06l-5-5a.75.75 0 010-1.06l5-5a.75.75 0 011.06 0z" clipRule="evenodd" />
              </svg>
            </a>
            <h1 className="text-lg font-semibold">Similarity graph</h1>
            {seedId && (
              <span className="text-sm text-base-content/70 ml-2 truncate">
                {seedTitle ? (
                  <>
                    {seedTitle}
                    <span className="text-xs text-base-content/40 font-mono ml-2">
                      {seedId}
                    </span>
                  </>
                ) : (
                  <span className="font-mono text-xs text-base-content/50">
                    seed: {seedId}
                  </span>
                )}
              </span>
            )}
            {error && (
              <span className="ml-auto text-xs text-error font-medium">{error}</span>
            )}
          </div>
        </header>

        <div ref={containerRef} className="relative min-h-0 w-full overflow-hidden">
          <ForceGraph2D
            ref={fgRef}
            graphData={fgData}
            width={size.w}
            height={size.h}
            backgroundColor="#000000"
            nodeId="id"
            nodeRelSize={4}
            nodeVal={nodeVal as any}
            nodeCanvasObject={drawNode as any}
            nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
              ctx.fill();
            }}
            linkColor={linkColor as any}
            linkWidth={linkWidth as any}
            onNodeHover={(node: any) => setHoverNode(node ? node.paper : null)}
            onNodeClick={(node: any) => expandNode(node.id, graph.mode)}
            cooldownTicks={120}
            d3VelocityDecay={0.35}
          />

          {/* Empty state when no ?seed= was provided */}
          {router.isReady && !seedId && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
              <div className="rounded-xl bg-[#111111] border border-[#333333] px-6 py-4 text-center max-w-md">
                <div className="text-base font-semibold text-base-content/80">
                  No seed paper selected
                </div>
                <div className="mt-1 text-xs text-base-content/50">
                  Open this page from a search result, or pass{" "}
                  <span className="font-mono">?seed=&lt;paper_id&gt;</span> in
                  the URL.
                </div>
              </div>
            </div>
          )}

          {/* Hover tooltip */}
          {hoverNode && (
            <div
              className="pointer-events-none absolute bottom-4 left-4 z-20 max-w-md rounded-xl bg-[#111111] border border-[#333333] p-3 shadow-lg"
            >
              <div className="text-sm font-semibold text-base-content">{hoverNode.title}</div>
              <div className="mt-1 text-xs text-base-content/60">
                {hoverNode.authors[0]}
                {hoverNode.authors.length > 1 ? ` +${hoverNode.authors.length - 1}` : ""}
              </div>
              <div className="mt-1 text-xs text-base-content/40 font-mono">
                {hoverNode.paper_id === seedId
                  ? "seed"
                  : `sim(seed) = ${(simToSeed[hoverNode.paper_id] ?? 0).toFixed(3)}`}
              </div>
            </div>
          )}

          {/* Controls panel (top-right floating) */}
          <aside
            className="absolute top-4 right-4 z-20 w-[320px] card bg-base-200 shadow-lg border border-[#333333]"
          >
            <div className="card-body gap-4 p-4">
              <div>
                <h2 className="card-title text-base">Mode</h2>
                <div className="mt-2 grid grid-cols-3 gap-1 rounded-lg bg-base-300 p-1">
                  {(["topk", "threshold", "mutual_knn"] as Mode[]).map((m) => (
                    <button
                      key={m}
                      onClick={() => setMode(m)}
                      className={`btn btn-xs ${
                        graph.mode === m ? "btn-primary" : "btn-ghost"
                      }`}
                    >
                      {MODE_LABEL[m]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">{slider.label}</span>
                  <span className="label-text-alt text-primary font-medium font-mono">
                    {slider.valueLabel}
                  </span>
                </label>
                <input
                  type="range"
                  min={slider.min}
                  max={slider.max}
                  step={slider.step}
                  value={slider.value}
                  onChange={(e) => slider.onChange(parseFloat(e.target.value))}
                  className="range range-primary range-sm"
                />
                <div className="mt-1 text-xs text-base-content/50">{slider.helper}</div>
              </div>

              {graph.mode === "threshold" && distribution && (
                <DistributionStrip
                  distribution={distribution}
                  threshold={graph.threshold}
                  min={slider.min}
                  max={slider.max}
                />
              )}

              <div className="text-xs text-base-content/50 leading-relaxed">
                <div>
                  nodes: {fgData.nodes.length}
                  {fgData.nodes.length !== graph.nodes.length && (
                    <span className="opacity-60">
                      {" "}
                      ({graph.nodes.length - fgData.nodes.length} hidden)
                    </span>
                  )}
                </div>
                <div>edges: {graph.edges.length}</div>
                <div>cached expansions: {Object.keys(graph.cache).length}</div>
                {loadingNodeId && (
                  <div className="text-warning mt-1">fetching {loadingNodeId}…</div>
                )}
              </div>

              <div className="text-[11px] text-base-content/40 leading-snug">
                Click any node to expand its top-{NEIGHBOR_CEILING} neighbors.
                Slider drags re-derive edges from cache without hitting the
                network.
              </div>
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// DistributionStrip — small percentile anchor under the threshold slider.
// ---------------------------------------------------------------------------

function DistributionStrip({
  distribution,
  threshold,
  min,
  max,
}: {
  distribution: SimilarityDistribution;
  threshold: number;
  min: number;
  max: number;
}) {
  const span = Math.max(1e-6, max - min);
  const ticks: { label: string; value: number }[] = [
    { label: "p50", value: distribution.p50 },
    { label: "p90", value: distribution.p90 },
    { label: "p95", value: distribution.p95 },
    { label: "p99", value: distribution.p99 },
    { label: "p99.5", value: distribution.p99_5 },
    { label: "p99.9", value: distribution.p99_9 },
  ];
  const pos = (v: number) =>
    `${Math.max(0, Math.min(100, ((v - min) / span) * 100))}%`;

  const markerStyle: CSSProperties = {
    left: pos(threshold),
  };

  return (
    <div className="rounded-md bg-base-300/60 px-2 py-2">
      {/* Tall enough to fit the rotated label text below the tick marks
          without overlap. Three of the six percentiles (p99/p99.5/p99.9)
          cluster very close together, so labels must rotate to read. */}
      <div className="relative h-14">
        {/* baseline */}
        <div className="absolute left-0 right-0 top-2 h-px bg-base-content/15" />
        {/* percentile ticks */}
        {ticks.map((t) => (
          <div
            key={t.label}
            className="absolute top-0 flex flex-col items-center"
            style={{ left: pos(t.value) }}
          >
            <div className="h-3 w-px bg-base-content/30" />
            <div
              className="mt-1 text-[9px] text-base-content/50 font-mono whitespace-nowrap origin-top-left"
              style={{ transform: "rotate(45deg)" }}
            >
              {t.label} ({t.value.toFixed(2)})
            </div>
          </div>
        ))}
        {/* current threshold marker */}
        <div
          className="absolute -translate-x-1/2 top-0 bottom-0 flex flex-col items-center pointer-events-none"
          style={markerStyle}
        >
          <div className="h-full w-px bg-primary" />
        </div>
      </div>
      <div className="mt-1 text-[10px] text-base-content/50 font-mono">
        {percentileLabel(threshold, distribution)}
      </div>
    </div>
  );
}

function percentileLabel(t: number, d: SimilarityDistribution): string {
  const points: Array<[string, number]> = [
    ["50th", d.p50],
    ["90th", d.p90],
    ["95th", d.p95],
    ["99th", d.p99],
    ["99.5th", d.p99_5],
    ["99.9th", d.p99_9],
  ];
  // Find which named percentile the threshold falls just above.
  let label = "<50th";
  for (const [name, value] of points) {
    if (t >= value) label = name;
  }
  return `T = ${t.toFixed(3)} (≈ ${label} percentile of corpus)`;
}
