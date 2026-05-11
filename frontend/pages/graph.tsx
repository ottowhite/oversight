import Head from "next/head";
import { useRouter } from "next/router";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ComponentType,
} from "react";

// react-force-graph-2d touches `window` at import time, so it must be
// loaded only on the client. We previously used next/dynamic for this,
// but next/dynamic in Next 12 doesn't reliably forward refs to the inner
// component, so the imperative API (d3Force, d3ReheatSimulation, etc.)
// was unreachable. Lazy-loading the module via a useEffect inside the
// component lets us render the real component directly and forward the
// ref natively.
//
// The module is module-cached, so subsequent mounts get the resolved
// component synchronously after the first import has settled.
let cachedForceGraph2D: ComponentType<any> | null = null;
let forceGraph2DPromise: Promise<ComponentType<any>> | null = null;
function loadForceGraph2D(): Promise<ComponentType<any>> {
  if (cachedForceGraph2D) return Promise.resolve(cachedForceGraph2D);
  if (forceGraph2DPromise) return forceGraph2DPromise;
  forceGraph2DPromise = import("react-force-graph-2d").then((mod) => {
    cachedForceGraph2D = mod.default as ComponentType<any>;
    return cachedForceGraph2D;
  });
  return forceGraph2DPromise;
}

// ---------------------------------------------------------------------------
// API contract types — must match docs/similarity-graph-plan.md exactly.
// When Phase 2 swaps in the real backend, these types are reused as-is.
// ---------------------------------------------------------------------------

type Paper = {
  paper_id: string;
  title: string;
  authors: string[];
  // Optional rich metadata returned by /api/papers/<id>/neighbors. Used by
  // the citation label rendered inside each node and by the abstract
  // sidebar panel. Optional because the API contract in the plan only
  // hard-guarantees paper_id/title/authors.
  paper_date?: string | null;
  abstract?: string | null;
  link?: string | null;
  source?: string | null;
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

// Note: `edges` is NOT stored in GraphState. It's a pure derivation
// from (cache, clickedIds, mode, k, threshold) and is recomputed via
// useMemo on every render. Storing it would invite the URL-vs-graph
// drift bug from round 5: dropping a paper from ?papers= via the back
// button leaves stale edges in state for the dropped cluster.
type GraphState = {
  nodes: Paper[];
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

// Module-scoped in-flight registry. React StrictMode + the bootstrap
// effect's deps array can fire expandNode twice in the same tick for
// the same paper-id; without dedup we'd hit /neighbors twice. Module
// scope (rather than per-component useRef) survives StrictMode's
// double-mount so a remount doesn't restart inflight requests either.
//
// The key is ${paperId}:${mutual} so a topk request and a mutual-kNN
// request for the same paper don't share a slot.
const inflightNeighbors = new Map<string, Promise<NeighborsResponse>>();

async function fetchNeighbors(
  paperId: string,
  opts: { k: number; mutual: boolean },
): Promise<NeighborsResponse> {
  const key = `${paperId}:${opts.mutual ? "1" : "0"}:k=${opts.k}`;
  const existing = inflightNeighbors.get(key);
  if (existing) return existing;

  const params = new URLSearchParams({
    k: String(opts.k),
    mutual: opts.mutual ? "true" : "false",
  });
  const promise = (async () => {
    try {
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
    } finally {
      // Clear the slot after settle so a future call can refetch (e.g.
      // a different `k` value) and a failed call doesn't stick around.
      inflightNeighbors.delete(key);
    }
  })();
  inflightNeighbors.set(key, promise);
  return promise;
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
  clickedIds: readonly string[],
  mode: Mode,
  k: number,
  threshold: number,
): GraphEdge[] {
  // Only derive edges for currently-clicked papers. The cache itself
  // persists across clickedIds changes (so a back-then-forward
  // round-trip is instant), but the rendered graph must track the URL
  // exactly: dropping a paper from ?papers= must drop its cluster.
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  for (const id of clickedIds) {
    const entry = cache[id];
    if (!entry) continue;
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
      // endpoints are clicked papers.
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

const SIDEBAR_OPEN_PX = 360;
const SIDEBAR_COLLAPSED_PX = 32;
const SIDEBAR_STORAGE_KEY = "oversight.graphSidebar.open";
// Floating controls panel (mode tabs / slider / percentile strip). Lives
// over the top-left of the canvas. Default closed so the canvas reads
// cleanly on first visit; user opens it on tap. State persisted across
// reloads.
const CONTROLS_STORAGE_KEY = "oversight.graphControls.open";

const MODE_LABEL: Record<Mode, string> = {
  topk: "top-k",
  threshold: "threshold",
  // "mutual-kNN" wraps in the floating panel's snug 3-column tab grid
  // (288px panel, ~76px per tab). The kNN suffix is implicit since the
  // whole UI is a kNN similarity graph, so "mutual" is unambiguous.
  mutual_knn: "mutual",
};

export default function GraphPage() {
  const router = useRouter();
  // The URL is the source of truth for which papers the user has
  // actively chosen ("clicked"). ?papers=A,B,C  → ["A", "B", "C"]
  // (insertion order = click order). Each clicked paper sits at the
  // center of a small cluster of its top-N neighbors.
  //
  // router.query is empty until router.isReady on first client render,
  // so we return [] until then to avoid spurious fetches.
  const clickedIds = useMemo<string[]>(() => {
    if (!router.isReady) return [];
    const raw = router.query.papers;
    const value = typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : "";
    if (!value) return [];
    return value
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  }, [router.isReady, router.query.papers]);
  const clickedSet = useMemo(() => new Set(clickedIds), [clickedIds]);

  const [graph, setGraph] = useState<GraphState>({
    nodes: [],
    mode: "topk",
    k: DEFAULT_K,
    threshold: 0,
    cache: {},
  });
  const [distribution, setDistribution] = useState<SimilarityDistribution | null>(null);
  // Side-panel paper resolution:
  //   hoverId is a transient overlay, set on mouse-enter and cleared on
  //   mouse-leave. pinnedId persists — set when the user clicks a node.
  //   Effective panel paper = hoverId ?? pinnedId.
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [loadingNodeId, setLoadingNodeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Right-side bar — pure paper preview, full height. Collapsible so the
  // graph can reclaim the full canvas width. Default open. Persist across
  // reloads via localStorage.
  const [sidebarOpen, setSidebarOpenRaw] = useState<boolean>(true);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (stored !== null) setSidebarOpenRaw(stored === "1");
  }, []);
  const setSidebarOpen = useCallback((open: boolean) => {
    setSidebarOpenRaw(open);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, open ? "1" : "0");
    }
  }, []);

  // Floating controls panel (top-left of canvas). Default CLOSED so the
  // canvas reads cleanly on first visit; user opens it on tap.
  const [controlsOpen, setControlsOpenRaw] = useState<boolean>(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(CONTROLS_STORAGE_KEY);
    if (stored !== null) setControlsOpenRaw(stored === "1");
  }, []);
  const setControlsOpen = useCallback((open: boolean) => {
    setControlsOpenRaw(open);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(CONTROLS_STORAGE_KEY, open ? "1" : "0");
    }
  }, []);

  // Force-graph imperative handle for fit-to-view / reheat.
  const fgRef = useRef<any>(null);
  // When set, the next onEngineStop fires zoomToFit and clears the
  // flag. Set whenever the visible graph fundamentally changes (mount,
  // clickedIds change, mode switch). The deferred-until-stop pattern is
  // necessary because zoomToFit needs node positions, which only exist
  // after the simulation has run a few ticks.
  const pendingFitRef = useRef<boolean>(true);
  // The library is dynamically imported so its window-touching code
  // doesn't run during SSR. Once loaded we render it directly (no
  // next/dynamic wrapper) so the ref forwards through to the real
  // component and its imperative API is reachable.
  const [ForceGraphCmp, setForceGraphCmp] = useState<ComponentType<any> | null>(
    cachedForceGraph2D,
  );
  useEffect(() => {
    if (cachedForceGraph2D) return;
    let cancelled = false;
    loadForceGraph2D().then((Cmp) => {
      if (!cancelled) setForceGraphCmp(() => Cmp);
    });
    return () => {
      cancelled = true;
    };
  }, []);
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

          // Walk responses in the same order as `tasks`. Each NeighborApiEntry
          // carries the rich metadata the UI needs (citation label, abstract
          // panel) — copy it all through so a hover doesn't need a re-fetch.
          const copyMetadata = (n: NeighborApiEntry | Paper): Paper => ({
            paper_id: n.paper_id,
            title: n.title,
            authors: n.authors,
            paper_date: (n as Paper).paper_date ?? null,
            abstract: (n as Paper).abstract ?? null,
            link: (n as Paper).link ?? null,
            source: (n as Paper).source ?? null,
          });
          let idx = 0;
          if (!haveTop) {
            const r = responses[idx++];
            nextEntry.topN = r.neighbors.map((n) => ({
              paper_id: n.paper_id,
              similarity: n.similarity,
            }));
            // Make sure the seed itself is in the node set with rich metadata.
            newPapers.push(copyMetadata(r.seed));
            for (const n of r.neighbors) newPapers.push(copyMetadata(n));
          }
          if (needMutual && !haveMutual) {
            const r = responses[idx++];
            nextEntry.mutualN = r.neighbors.map((n) => ({
              paper_id: n.paper_id,
              similarity: n.similarity,
            }));
            // Mutual-kNN may surface papers we haven't seen in top-N.
            for (const n of r.neighbors) newPapers.push(copyMetadata(n));
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

          // edges is derived (useMemo on the render side); no need to
          // recompute it here.
          return { ...g, cache, nodes: merged };
        });
      } catch (err) {
        setError(String(err));
      } finally {
        setLoadingNodeId(null);
      }
    },
    [graph.cache],
  );

  // Fetch any clicked paper that isn't yet cached. Re-runs whenever the
  // URL's ?papers= list changes (back/forward, clicks, deep links). Each
  // expandNode call is idempotent — a cache hit returns immediately.
  useEffect(() => {
    if (clickedIds.length === 0) return;
    for (const id of clickedIds) {
      expandNode(id, graph.mode);
    }
    // We intentionally depend only on clickedIds + mode — expandNode
    // closes over the current cache and skips on hits, so re-deriving
    // it on every state change would just create extra work.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clickedIds, graph.mode]);

  // Reset pinned/hover state when the URL no longer reflects the user
  // action that established it. clickPaper sets pinnedId at the same
  // time it pushes the id into ?papers=; the symmetric back-nav must
  // undo both. Without this, a click → back leaves the side panel
  // stuck on the abstract of a paper the user just dismissed.
  //
  // Pin clears when the paper falls out of clickedIds even if it's
  // still on-canvas as a neighbor — the user's "I want to read this"
  // action was tied to the click, and back-nav undoes that action.
  // Hover is transient and only clears when the paper is unreachable
  // entirely (gone from the graph), since the natural mouse-leave
  // already handles the common case.
  useEffect(() => {
    if (pinnedId && !clickedSet.has(pinnedId)) setPinnedId(null);
    if (hoverId) {
      const reachable = new Set<string>(clickedIds);
      for (const id of clickedIds) {
        const entry = graph.cache[id];
        if (!entry) continue;
        for (const n of entry.topN) reachable.add(n.paper_id);
        if (entry.mutualN) for (const n of entry.mutualN) reachable.add(n.paper_id);
      }
      if (!reachable.has(hoverId)) setHoverId(null);
    }
  }, [clickedIds, clickedSet, graph.cache, pinnedId, hoverId]);


  // -------------------------------------------------------------------------
  // Slider / mode handlers (pure cache-derived re-renders).
  // -------------------------------------------------------------------------

  const setMode = useCallback(
    async (mode: Mode) => {
      setGraph((g) => ({
        ...g,
        mode,
        threshold:
          mode === "threshold" && g.threshold === 0 && distribution
            ? distribution.p99
            : g.threshold,
      }));
      // Entering mutual-kNN: fetch the mutual edge set for every clicked
      // paper that doesn't have it yet. Each expandNode call is
      // idempotent so this is safe to fire-and-forget.
      if (mode === "mutual_knn") {
        for (const id of clickedIds) {
          const entry = graph.cache[id];
          if (!entry || !entry.mutualN) {
            expandNode(id, "mutual_knn");
          }
        }
      }
    },
    [distribution, graph.cache, clickedIds, expandNode],
  );

  const setK = useCallback((k: number) => {
    setGraph((g) => ({ ...g, k }));
  }, []);

  const setThreshold = useCallback((t: number) => {
    setGraph((g) => ({ ...g, threshold: t }));
  }, []);

  // Click → pin + (if not yet clicked) push to URL. The URL push
  // triggers the bootstrap effect, which fires expandNode for the new
  // id. Already-clicked papers are still pinned to the panel but the
  // URL is left unchanged.
  const clickPaper = useCallback(
    (paperId: string) => {
      setPinnedId(paperId);
      if (clickedSet.has(paperId)) return;
      const next = [...clickedIds, paperId];
      router.push(
        { pathname: "/graph", query: { papers: next.join(",") } },
        undefined,
        { shallow: true },
      );
    },
    [clickedIds, clickedSet, router],
  );

  // -------------------------------------------------------------------------
  // Derived graph data for ForceGraph2D.
  // -------------------------------------------------------------------------

  // Edges are derived purely from (cache, clickedIds, mode, slider).
  // No state lives here — this is what makes the URL the single source
  // of truth. Dropping a paper from ?papers= via the back button drops
  // its cluster on the very next render.
  const edges = useMemo(
    () => deriveEdges(graph.cache, clickedIds, graph.mode, graph.k, graph.threshold),
    [graph.cache, clickedIds, graph.mode, graph.k, graph.threshold],
  );

  // Whenever the visible graph fundamentally changes — clickedIds, mode,
  // or the edge count (which a slider drag in topk/threshold can shrink
  // dramatically) — request a fit-to-view. The actual zoomToFit call
  // happens inside onEngineStop once node positions exist.
  useEffect(() => {
    pendingFitRef.current = true;
    // Gentle reheat so the layout settles into the changed graph without
    // shocking existing nodes back to alpha=1 (which whips the whole
    // cluster around when a single neighbor is added).
    const fg = fgRef.current;
    if (fg && typeof fg.d3ReheatSimulation === "function") {
      fg.d3ReheatSimulation();
    }
  }, [clickedIds, graph.mode, edges.length]);

  // Persist node objects across renders so d3-force keeps each node's
  // x/y/vx/vy state intact (the lib mutates input objects in place). If
  // we passed fresh wrappers every render, every node would be treated
  // as "new" and the simulation would re-shock from scratch on every
  // slider drag or expansion.
  //
  // The map is keyed by paper_id; we add entries on first appearance and
  // never delete (a small leak vs. a big jank fix).
  const nodeObjRef = useRef<Map<string, any>>(new Map());

  const fgData = useMemo(() => {
    // Hide nodes that have no edges in the current derived view,
    // otherwise top-k with k<20 (or threshold mode) leaves orphan nodes
    // floating disconnected. The cache still holds them, so they reappear
    // instantly when the slider widens — no re-fetch needed.
    //
    // Clicked papers always render even if every edge filtered out, so
    // the user can always see "what they've explored."
    const connected = new Set<string>(clickedIds);
    for (const e of edges) {
      connected.add(typeof e.source === "string" ? e.source : String(e.source));
      connected.add(typeof e.target === "string" ? e.target : String(e.target));
    }

    // For pre-positioning newly-added nodes, build a quick lookup of
    // each cached neighbor → its parent (the clicked paper that pulled
    // it in). When we first render a new neighbor, seed its x/y near
    // the parent's current position so d3-force doesn't have to fly it
    // in from (0, 0), which whips the existing layout around.
    const parentOf = new Map<string, string>();
    for (const id of clickedIds) {
      const entry = graph.cache[id];
      if (!entry) continue;
      const list = entry.topN.concat(entry.mutualN ?? []);
      for (const n of list) {
        if (!parentOf.has(n.paper_id) && n.paper_id !== id) {
          parentOf.set(n.paper_id, id);
        }
      }
    }

    const objs = nodeObjRef.current;
    const nodes = graph.nodes
      .filter((p) => connected.has(p.paper_id))
      .map((p) => {
        let n = objs.get(p.paper_id);
        if (!n) {
          n = { id: p.paper_id, paper: p };
          // Seed position near the parent (if any). Without this, every
          // new node spawns at (0, 0) and the simulation has to drag it
          // out — visible as a "pull toward origin" of the whole graph.
          // Small jitter so coincident nodes don't share exact coords
          // (d3-force handles coincident points poorly).
          const parentId = parentOf.get(p.paper_id);
          const parent = parentId ? objs.get(parentId) : null;
          if (parent && typeof parent.x === "number" && typeof parent.y === "number") {
            n.x = parent.x + (Math.random() - 0.5) * 30;
            n.y = parent.y + (Math.random() - 0.5) * 30;
          }
          objs.set(p.paper_id, n);
        } else {
          // Refresh paper metadata in case it was enriched by a later
          // fetch (e.g. an abstract that arrived after the initial
          // top-k call). Identity-stable so d3-force still treats it
          // as the same node.
          n.paper = p;
        }
        return n;
      });
    const links = edges.map((e) => ({
      source: e.source,
      target: e.target,
      similarity: e.similarity,
    }));
    return { nodes, links };
  }, [graph.nodes, edges, clickedIds, graph.cache]);

  // Per-node degree, for sizing.
  const degreeById = useMemo(() => {
    const d: Record<string, number> = {};
    for (const e of edges) {
      d[e.source] = (d[e.source] ?? 0) + 1;
      d[e.target] = (d[e.target] ?? 0) + 1;
    }
    return d;
  }, [edges]);

  // For each paper, compute max similarity to any clicked paper. Drives
  // the panel's "sim = X.XXX" display. Clicked papers themselves get
  // sim 1.0 (against themselves).
  const simToClicked = useMemo(() => {
    const m: Record<string, number> = {};
    for (const id of clickedIds) m[id] = 1.0;
    for (const id of clickedIds) {
      const entry = graph.cache[id];
      if (!entry) continue;
      for (const n of entry.topN) {
        const prev = m[n.paper_id] ?? 0;
        if (n.similarity > prev) m[n.paper_id] = n.similarity;
      }
    }
    return m;
  }, [graph.cache, clickedIds]);

  // Look up paper metadata by id (for the panel and header). Built
  // inline because we touch graph.nodes once and don't want to thread
  // a Map through the JSX.
  const paperById = useMemo(() => {
    const m: Record<string, Paper> = {};
    for (const p of graph.nodes) m[p.paper_id] = p;
    return m;
  }, [graph.nodes]);

  // -------------------------------------------------------------------------
  // Visual helpers.
  // -------------------------------------------------------------------------

  // Per-render normalization: stretch the visible link-similarity range
  // across the visual encoding so a graph with sims clustered in 0.7–0.85
  // shows clear contrast between its weakest and strongest edges. Without
  // normalization, a narrow input range would all map to similarly-thick
  // similarly-opaque lines and lose all signal.
  //
  // The `degenerate` flag fires when there's a single edge (or every
  // edge has identical similarity). In that case the lerp would map
  // every edge to norm=0 (the floor of the visual range) → invisible
  // hairline. Treat degenerate ranges as "all edges are the strongest
  // visible" and return norm=1 instead, so the user sees a bold line
  // rather than a vanishingly thin one.
  const linkSimRange = useMemo(() => {
    if (edges.length === 0) return { lo: 0.5, hi: 0.9, degenerate: false };
    let lo = Infinity;
    let hi = -Infinity;
    for (const e of edges) {
      if (e.similarity < lo) lo = e.similarity;
      if (e.similarity > hi) hi = e.similarity;
    }
    return { lo, hi, degenerate: hi - lo < 1e-3 };
  }, [edges]);

  const normSim = useCallback(
    (s: number) => {
      const { lo, hi, degenerate } = linkSimRange;
      if (degenerate) return 1;
      return Math.max(0, Math.min(1, (s - lo) / (hi - lo)));
    },
    [linkSimRange],
  );

  const linkColor = useCallback(
    (link: any) => {
      const s = typeof link.similarity === "number" ? link.similarity : 0.5;
      const norm = normSim(s);
      // Vercel blue (#0070f3 = 0,112,243) at variable opacity. Wider
      // alpha range than before (0.12 → 0.95) so the strongest visible
      // edge reads as nearly opaque while the weakest is a faint ghost.
      const alpha = (0.12 + norm * 0.83).toFixed(3);
      return `rgba(0, 112, 243, ${alpha})`;
    },
    [normSim],
  );

  const linkWidth = useCallback(
    (link: any) => {
      // Width is the primary similarity signal. Stretch the visual
      // range across the per-render observed sim min/max so intra-graph
      // contrast is dramatic even when raw sims sit in a narrow band
      // (e.g. all edges between 0.70 and 0.84). Floor at 0.5px so even
      // weak edges are visible; ~8px ceiling so strong edges read as
      // bold connections.
      const s = typeof link.similarity === "number" ? link.similarity : 0.5;
      const norm = normSim(s);
      return 0.5 + norm * 7.5;
    },
    [normSim],
  );

  // Citation labels live INSIDE the node circle now, in world coordinates
  // so text and circle scale together with zoom. Each node's radius is
  // grown to fit its label (with padding); the force simulation then
  // pushes overlapping nodes apart via collision detection driven by
  // nodeVal/nodeRelSize.
  //
  // Layout constants are in world units (the same units the d3-force
  // simulation uses for x/y). NODE_FONT_PX is a world-space size, NOT a
  // screen-pixel size.
  // World-coordinate sizes. Bumping NODE_FONT_PX makes citations easier
  // to read at default zoom; multi-line wrap keeps the resulting circles
  // from ballooning in width.
  const NODE_FONT_PX = 8; // world-units; ~2× the previous single-line font
  const NODE_LINE_HEIGHT = NODE_FONT_PX * 1.2;
  const NODE_TEXT_PAD = 4; // world-units of internal padding
  const NODE_MIN_RADIUS = 10; // floor for short single-line labels
  const NODE_WRAP_TARGET_CHARS = 12; // greedy line-fill target
  const NODE_REL_SIZE = 1; // px per sqrt(nodeVal) unit; we fully drive radius via nodeVal
  // Neighbor nodes render smaller and dimmer than clicked nodes so the
  // user's eye picks out the papers they've actively chosen.
  const NEIGHBOR_FONT_SCALE = 0.7;
  const NEIGHBOR_OPACITY = 0.6;

  // Cache wrapped label + measured dimensions per paper_id. Wrapping +
  // measuring is done once on first render of each node and re-used for
  // every subsequent frame. Off-screen canvas so measurement is
  // zoom-independent.
  type LabelInfo = {
    lines: string[];
    worldWidth: number; // widest measured line
    worldHeight: number; // total stack height (lines * lineHeight)
  };
  const labelCache = useRef<Map<string, LabelInfo>>(new Map());
  const measureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const getLabelInfo = useCallback(
    (paper: Paper | undefined, paperId: string): LabelInfo => {
      const cached = labelCache.current.get(paperId);
      if (cached) return cached;
      const label = formatCitation(paper);
      const lines = label ? wrapLabel(label, NODE_WRAP_TARGET_CHARS) : [];
      if (!measureCanvasRef.current) {
        measureCanvasRef.current = document.createElement("canvas");
      }
      const mctx = measureCanvasRef.current.getContext("2d");
      let worldWidth = 0;
      if (mctx) {
        mctx.font = `${NODE_FONT_PX}px ui-sans-serif, system-ui, sans-serif`;
        for (const line of lines) {
          worldWidth = Math.max(worldWidth, mctx.measureText(line).width);
        }
      } else {
        // Fallback estimate when 2D context is unavailable (~test envs).
        for (const line of lines) {
          worldWidth = Math.max(worldWidth, line.length * NODE_FONT_PX * 0.6);
        }
      }
      const worldHeight = lines.length * NODE_LINE_HEIGHT;
      const info: LabelInfo = { lines, worldWidth, worldHeight };
      labelCache.current.set(paperId, info);
      return info;
    },
    [NODE_LINE_HEIGHT],
  );

  // Per-node world radius. Combines a degree-based "base" radius with the
  // size of the wrapped label so the citation always fits inside the
  // circle without clipping. The diagonal-half (sqrt(w² + h²) / 2) is the
  // tightest fit; we use that plus padding.
  const nodeRadius = useCallback(
    (node: any) => {
      const deg = degreeById[node.id] ?? 0;
      const isClicked = clickedSet.has(node.id);
      // Clicked papers read as hubs even before their neighbors connect
      // back. Neighbors render at ~60% the radius of clicked papers so
      // the eye picks out which papers the user has actively chosen.
      // Citation text scales down proportionally for neighbors via
      // getLabelInfo's font-size (handled in drawNode).
      const baseRadius = (isClicked ? 5 : 2) + Math.sqrt(deg) * 0.8;
      const { worldWidth, worldHeight } = getLabelInfo(node.paper, node.id);
      // For neighbors we use a smaller font-block, so shrink the label
      // bound proportionally too (NEIGHBOR_FONT_SCALE matches drawNode).
      const labelScale = isClicked ? 1 : NEIGHBOR_FONT_SCALE;
      const w = worldWidth * labelScale;
      const h = worldHeight * labelScale;
      const labelRadius =
        Math.sqrt(w * w + h * h) / 2 + NODE_TEXT_PAD;
      const minR = isClicked ? NODE_MIN_RADIUS : NODE_MIN_RADIUS * 0.7;
      return Math.max(minR, baseRadius, labelRadius);
    },
    [degreeById, clickedSet, getLabelInfo],
  );

  // nodeVal feeds both the d3-force collision force and the click-hit
  // area. Final pixel radius from the lib is sqrt(nodeVal) * nodeRelSize,
  // and we set nodeRelSize=1, so nodeVal = radius^2 makes the lib agree
  // with our drawNode radius.
  const nodeVal = useCallback(
    (node: any) => {
      const r = nodeRadius(node);
      return r * r;
    },
    [nodeRadius],
  );

  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, _globalScale: number) => {
      const isLoading = loadingNodeId === node.id;
      const isClicked = clickedSet.has(node.id);
      const isPinned = node.id === pinnedId;
      const r = nodeRadius(node);

      // 1) Circle. Clicked papers use a darker blue to lift contrast
      //    with the white citation text. Neighbors share the same hue
      //    at NEIGHBOR_OPACITY so the eye picks out the user's actively
      //    chosen papers. Pinned (a clicked paper currently driving the
      //    side-panel) gets a subtle white halo to mark it as "active."
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI, false);
      ctx.fillStyle = isClicked
        ? "rgba(0, 60, 140, 1)" // darker so white text reads crisper
        : `rgba(0, 80, 168, ${NEIGHBOR_OPACITY})`;
      ctx.fill();
      // Stroke: loading > pinned > clicked > neighbor.
      ctx.strokeStyle = isLoading
        ? "#f5a623"
        : isPinned
          ? "rgba(255,255,255,0.95)"
          : isClicked
            ? "rgba(255,255,255,0.7)"
            : "rgba(255,255,255,0.25)";
      ctx.lineWidth = isPinned ? 1.5 : isClicked ? 0.8 : 0.4;
      ctx.stroke();
      // Pinned glow: a second translucent ring just outside the stroke.
      if (isPinned) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI, false);
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.lineWidth = 1.0;
        ctx.stroke();
      }

      // 2) Citation label centered inside the circle, possibly across
      //    multiple lines. Both the font and radius are in world coords,
      //    so they scale together with zoom and never smear. Neighbors
      //    get a smaller font (NEIGHBOR_FONT_SCALE) to match the smaller
      //    circle and reduce visual weight.
      const { lines } = getLabelInfo(node.paper, node.id);
      if (lines.length === 0) return;
      const fontPx = isClicked ? NODE_FONT_PX : NODE_FONT_PX * NEIGHBOR_FONT_SCALE;
      const lineHeight = fontPx * 1.2;
      // Bumping clicked-node weight from regular to 600 reads as a
      // crisp label rather than a thin overlay, especially against the
      // darker-blue fill we picked above.
      const fontWeight = isClicked ? 600 : 400;
      ctx.font = `${fontWeight} ${fontPx}px ui-sans-serif, system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      // Vertically center the stack.
      const topY = node.y - ((lines.length - 1) * lineHeight) / 2;
      // Text-stroke under the fill cleans up the AA on bright pixels —
      // the eye reads the label as solid letters instead of a smear.
      // Stroke matches the circle fill so the result is anti-aliased
      // crispness rather than a visible outline.
      if (isClicked) {
        ctx.strokeStyle = "rgba(0, 60, 140, 1)";
        ctx.lineWidth = 0.6;
        for (let i = 0; i < lines.length; i++) {
          ctx.strokeText(lines[i], node.x, topY + i * lineHeight);
        }
      }
      ctx.fillStyle = isClicked
        ? "rgba(255,255,255,1)"
        : "rgba(237,237,237,0.85)";
      for (let i = 0; i < lines.length; i++) {
        ctx.fillText(lines[i], node.x, topY + i * lineHeight);
      }
    },
    [loadingNodeId, clickedSet, pinnedId, nodeRadius, getLabelInfo],
  );

  // Reset the label cache when the cache shape changes (new paper added),
  // so that newly-fetched neighbors get a fresh measurement and grow
  // their nodes to fit.
  useEffect(() => {
    labelCache.current.clear();
  }, [graph.cache]);

  // d3-force tuning. Reach into the simulation via the imperative API
  // exposed by react-force-graph-2d. When loaded through next/dynamic the
  // ref isn't always forwarded to the inner component (Next 12 quirk),
  // so guard everything and silently skip if the imperative methods
  // aren't reachable — visual encoding via linkColor/linkWidth still
  // communicates similarity to the user.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || typeof fg.d3Force !== "function") return;
    const linkForce = fg.d3Force("link");
    if (linkForce && typeof linkForce.distance === "function") {
      // Map similarity 0.30..0.85 → distance 320..160 (world units).
      // Citation labels live INSIDE each circle now, which makes nodes
      // ~12-40 world units wide. Two adjacent nodes need their CENTERS
      // at least (r1+r2) apart just to not overlap; bumping rest length
      // gives the layout the room it needs.
      linkForce.distance((link: any) => {
        const s = typeof link.similarity === "number" ? link.similarity : 0.5;
        const norm = Math.max(0, Math.min(1, (s - 0.3) / 0.55));
        return 320 - norm * 160;
      });
    }
    if (linkForce && typeof linkForce.strength === "function") {
      linkForce.strength((link: any) => {
        const s = typeof link.similarity === "number" ? link.similarity : 0.5;
        return Math.max(0.05, Math.min(1, (s - 0.2) * 1.5));
      });
    }
    // Stronger repulsion so wide-text nodes don't pile up. Default
    // d3-forceManyBody strength is -30; bump to -800 to match the much
    // larger node radii.
    const chargeForce = fg.d3Force("charge");
    if (chargeForce && typeof chargeForce.strength === "function") {
      chargeForce.strength(-800);
    }
    // Pad the collision radius a few world units so labels never clip.
    // The lib's own collide accessor uses sqrt(val)*nodeRelSize which
    // already matches nodeRadius() in our setup; we just add a margin.
    const collideForce = fg.d3Force("collide");
    if (collideForce && typeof collideForce.radius === "function") {
      collideForce.radius((node: any) => nodeRadius(node) + 4);
      if (typeof collideForce.iterations === "function") {
        collideForce.iterations(2); // tighter packing in fewer ticks
      }
    }
    if (typeof fg.d3ReheatSimulation === "function") {
      fg.d3ReheatSimulation();
    }
    // ForceGraphCmp is in the deps so the effect re-runs after the
    // lazy import resolves and fgRef.current finally points at a real
    // forwardRef-bound instance. Without it, the only first run sees
    // fgRef.current === null and bails.
  }, [fgData, nodeRadius, ForceGraphCmp]);

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
      <main className="grid h-screen grid-rows-[auto,1fr] overflow-hidden">
        {/* Top-level header spans both the graph and the abstract panel.
            overflow-hidden + min-w-0 on the inner flex prevent any child
            (long error text, future title content) from stretching the
            page off-screen. */}
        <header className="border-b border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40 overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 min-w-0">
            <a
              href="/"
              className="btn btn-ghost btn-sm btn-circle shrink-0"
              title="Back to search"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                <path fillRule="evenodd" d="M9.78 4.22a.75.75 0 010 1.06L6.06 9h11.69a.75.75 0 010 1.5H6.06l3.72 3.72a.75.75 0 11-1.06 1.06l-5-5a.75.75 0 010-1.06l5-5a.75.75 0 011.06 0z" clipRule="evenodd" />
              </svg>
            </a>
            <h1 className="text-lg font-semibold shrink-0">Similarity graph</h1>
            {clickedIds.length > 0 && (
              <span className="text-sm text-base-content/70 shrink-0">
                Exploring {clickedIds.length} paper
                {clickedIds.length === 1 ? "" : "s"}
              </span>
            )}
            {error && (
              <span className="ml-auto min-w-0 truncate text-xs text-error font-medium">
                {error}
              </span>
            )}
          </div>
        </header>

        {/* Content row: graph canvas (flex) + collapsible right-side bar.
            Width of the bar drives the grid template; the canvas reflows
            to fill whatever's left over. minmax(0, 1fr) instead of 1fr is
            the canonical fix for grid children overflowing their track —
            the implicit min-width: auto on grid items lets intrinsic
            content push the column wider than its share. */}
        <div
          className="grid min-h-0 min-w-0 overflow-hidden"
          style={{
            gridTemplateColumns: `minmax(0, 1fr) ${sidebarOpen ? SIDEBAR_OPEN_PX : SIDEBAR_COLLAPSED_PX}px`,
          }}
        >
          <div
            ref={containerRef}
            className="relative min-h-0 min-w-0 w-full overflow-hidden"
          >
            {ForceGraphCmp && (
              <ForceGraphCmp
                ref={fgRef}
                graphData={fgData}
                width={size.w}
                height={size.h}
                backgroundColor="#000000"
                nodeId="id"
                nodeRelSize={NODE_REL_SIZE}
                nodeVal={nodeVal as any}
                nodeCanvasObject={drawNode as any}
                nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                  // Hit area = the same circle we draw, so the entire
                  // label is clickable / hoverable. nodeRadius is in
                  // world units; the lib applies the current zoom
                  // transform itself.
                  ctx.fillStyle = color;
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, nodeRadius(node), 0, 2 * Math.PI, false);
                  ctx.fill();
                }}
                linkColor={linkColor as any}
                linkWidth={linkWidth as any}
                onNodeHover={(node: any) => {
                  // Hover is a transient overlay — set on enter, cleared
                  // on leave. The pinned paper (set by click) survives
                  // mouse-off so the user can read long abstracts.
                  setHoverId(node && node.id ? String(node.id) : null);
                }}
                onNodeClick={(node: any) => clickPaper(String(node.id))}
                onEngineStop={() => {
                  // Fit-to-view request was set by a meaningful change
                  // (mount, clickedIds change, mode switch, slider drag
                  // big enough to alter the edge count). Clear the flag
                  // before calling so a recursive zoom-induced re-stop
                  // doesn't re-fire.
                  if (!pendingFitRef.current) return;
                  pendingFitRef.current = false;
                  const fg = fgRef.current;
                  if (fg && typeof fg.zoomToFit === "function") {
                    // 400ms ease, 60px screen-padding around the
                    // bounding box of currently-rendered nodes.
                    fg.zoomToFit(400, 60);
                  }
                }}
                cooldownTicks={120}
                warmupTicks={0}
                d3AlphaDecay={0.05}
                d3VelocityDecay={0.4}
              />
            )}

            {/* Floating controls (top-left). Subtle icon button when
                closed; expands to a small panel containing mode tabs,
                slider, and percentile strip when opened. */}
            <FloatingControls
              open={controlsOpen}
              onOpenChange={setControlsOpen}
              mode={graph.mode}
              onModeChange={setMode}
              slider={slider}
              distribution={distribution}
              stats={{
                renderedNodes: fgData.nodes.length,
                totalNodes: graph.nodes.length,
                edges: edges.length,
                cachedExpansions: Object.keys(graph.cache).length,
                loadingNodeId,
              }}
            />

            {/* Empty state when no ?papers= was provided */}
            {router.isReady && clickedIds.length === 0 && (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
                <div className="rounded-xl bg-[#111111] border border-[#333333] px-6 py-4 text-center max-w-md pointer-events-auto">
                  <div className="text-base font-semibold text-base-content/80">
                    No papers selected
                  </div>
                  <div className="mt-1 text-xs text-base-content/50">
                    Open the graph from a search result, or pass{" "}
                    <span className="font-mono">
                      ?papers=&lt;id&gt;[,&lt;id&gt;…]
                    </span>{" "}
                    in the URL.
                  </div>
                  <a
                    href="/"
                    className="btn btn-primary btn-sm mt-3"
                  >
                    Back to search
                  </a>
                </div>
              </div>
            )}
          </div>

          {(() => {
            const panelId = hoverId ?? pinnedId;
            const panelPaper = panelId ? paperById[panelId] ?? null : null;
            return (
              <RightSidebar
                open={sidebarOpen}
                onToggle={() => setSidebarOpen(!sidebarOpen)}
                panelPaper={panelPaper}
                isClicked={!!panelPaper && clickedSet.has(panelPaper.paper_id)}
                isPinned={!!panelPaper && panelPaper.paper_id === pinnedId}
                similarity={
                  panelPaper ? simToClicked[panelPaper.paper_id] : undefined
                }
                onClearPanel={() => setPinnedId(null)}
              />
            );
          })()}
        </div>
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// AbstractPanel — fixed right-hand sidebar that shows the metadata and
// abstract for the most recently hovered node. Latches: never clears
// when the cursor leaves a node, only swaps to a new paper.
// ---------------------------------------------------------------------------

type SliderConfig = {
  label: string;
  valueLabel: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  helper: string;
};

type SidebarStats = {
  renderedNodes: number;
  totalNodes: number;
  edges: number;
  cachedExpansions: number;
  loadingNodeId: string | null;
};

// Right-side bar — pure paper preview, full height. Controls used to
// share this bar above the preview but moved out into a floating
// top-left panel in round 6 so the abstract gets the full vertical
// space. Collapsible to a 32px strip (just the toggle button) so the
// graph can reclaim the full canvas width when the user wants to focus
// on the layout.
function RightSidebar({
  open,
  onToggle,
  panelPaper,
  isClicked,
  isPinned,
  similarity,
  onClearPanel,
}: {
  open: boolean;
  onToggle: () => void;
  panelPaper: Paper | null;
  isClicked: boolean;
  isPinned: boolean;
  similarity: number | undefined;
  onClearPanel: () => void;
}) {
  return (
    <aside className="border-l border-base-300/60 bg-base-200/40 min-h-0 flex flex-col">
      {/* Top edge: collapse/expand toggle + clear button (when a paper
          is pinned). The toggle stays visible in both states so the
          user can always reopen. */}
      <div className="flex items-center justify-between border-b border-base-300/60 px-2 py-2">
        <button
          onClick={onToggle}
          title={open ? "Collapse sidebar" : "Expand sidebar"}
          className="btn btn-ghost btn-xs btn-square"
        >
          {/* Chevron rotates with the open state. Pointing INTO the bar
              (right) means "collapse," pointing OUT (left) means "expand." */}
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="h-4 w-4"
          >
            {open ? (
              <path
                fillRule="evenodd"
                d="M12.79 5.23a.75.75 0 010 1.06L9.06 10l3.73 3.71a.75.75 0 11-1.06 1.06l-4.25-4.24a.75.75 0 010-1.06l4.25-4.24a.75.75 0 011.06 0z"
                clipRule="evenodd"
              />
            ) : (
              <path
                fillRule="evenodd"
                d="M7.21 5.23a.75.75 0 011.06 0l4.25 4.24a.75.75 0 010 1.06l-4.25 4.24a.75.75 0 11-1.06-1.06L10.94 10 7.21 6.29a.75.75 0 010-1.06z"
                clipRule="evenodd"
              />
            )}
          </svg>
        </button>
        {open && panelPaper && (
          <button
            onClick={onClearPanel}
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

      {/* Body — only rendered when open. Pure preview surface, no
          section dividers. */}
      {open && (
        <div className="flex-1 min-h-0 overflow-y-auto p-4">
          <HoverPreview
            paper={panelPaper}
            isClicked={isClicked}
            isPinned={isPinned}
            similarity={similarity}
          />
        </div>
      )}
    </aside>
  );
}

// Floating controls panel anchored to the top-left of the canvas.
// Closed: a small semi-transparent icon button (~32px) so it doesn't
// dominate. Opened: a small panel with mode tabs, slider, percentile
// strip, and a stats footer. Click outside or the × → closes.
//
// Positioning uses absolute over the canvas (z-10 above the graph,
// below modal-style overlays). The icon button is positioned in the
// same top-left slot so the user's eye doesn't have to retarget when
// they open/close.
function FloatingControls({
  open,
  onOpenChange,
  mode,
  onModeChange,
  slider,
  distribution,
  stats,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: Mode;
  onModeChange: (m: Mode) => void;
  slider: SliderConfig;
  distribution: SimilarityDistribution | null;
  stats: SidebarStats;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Click-outside-to-close: register a document-level listener while
  // the panel is open and dismiss whenever a press lands outside the
  // panel surface. Use pointerdown in capture phase because
  // react-force-graph attaches its own pointer handlers on the canvas
  // that stop propagation — without capture, clicks on the graph
  // canvas wouldn't reach this handler.
  useEffect(() => {
    if (!open) return;
    const onDown = (ev: Event) => {
      const target = ev.target as Node | null;
      if (!target) return;
      if (panelRef.current && panelRef.current.contains(target)) return;
      onOpenChange(false);
    };
    document.addEventListener("pointerdown", onDown, true);
    return () => document.removeEventListener("pointerdown", onDown, true);
  }, [open, onOpenChange]);

  if (!open) {
    return (
      <button
        onClick={() => onOpenChange(true)}
        title="Show controls"
        className="absolute top-3 left-3 z-20 h-8 w-8 rounded-md border border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40 hover:bg-base-100/80 flex items-center justify-center text-base-content/70 hover:text-base-content transition-colors"
      >
        {/* Sliders icon — three horizontal lines with adjustable
            handles, the universal "controls/settings" affordance. */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-4 w-4"
        >
          <path
            fillRule="evenodd"
            d="M3 5a1 1 0 011-1h6a1 1 0 110 2H4a1 1 0 01-1-1zm10.5-1a2 2 0 100 4 2 2 0 000-4zM3 10a1 1 0 011-1h2a1 1 0 110 2H4a1 1 0 01-1-1zm6.5-1a2 2 0 100 4 2 2 0 000-4zM3 15a1 1 0 011-1h10a1 1 0 110 2H4a1 1 0 01-1-1zm14.5-1a2 2 0 100 4 2 2 0 000-4z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    );
  }

  return (
    <div
      ref={panelRef}
      className="absolute top-3 left-3 z-20 w-72 rounded-lg border border-base-300/60 bg-base-100/95 backdrop-blur shadow-xl"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-base-300/60">
        <span className="text-[11px] uppercase tracking-wider font-medium text-base-content/60">
          Controls
        </span>
        <button
          onClick={() => onOpenChange(false)}
          title="Hide controls"
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
      </div>
      <div className="p-3 flex flex-col gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider font-medium text-base-content/50 mb-2">
            Mode
          </div>
          <div className="grid grid-cols-3 gap-1 rounded-lg bg-base-300 p-1">
            {(["topk", "threshold", "mutual_knn"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => onModeChange(m)}
                className={`btn btn-xs ${
                  mode === m ? "btn-primary" : "btn-ghost"
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
          <div className="mt-1 text-xs text-base-content/50">
            {slider.helper}
          </div>
        </div>

        {mode === "threshold" && distribution && (
          <DistributionStrip
            distribution={distribution}
            threshold={slider.value}
            min={slider.min}
            max={slider.max}
          />
        )}

        <div className="text-xs text-base-content/50 leading-relaxed">
          <div>
            nodes: {stats.renderedNodes}
            {stats.renderedNodes !== stats.totalNodes && (
              <span className="opacity-60">
                {" "}
                ({stats.totalNodes - stats.renderedNodes} hidden)
              </span>
            )}
          </div>
          <div>edges: {stats.edges}</div>
          <div>cached expansions: {stats.cachedExpansions}</div>
          {stats.loadingNodeId && (
            <div className="text-warning mt-1">
              fetching {stats.loadingNodeId}…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HoverPreview({
  paper,
  isClicked,
  isPinned,
  similarity,
}: {
  paper: Paper | null;
  isClicked: boolean;
  isPinned: boolean;
  similarity: number | undefined;
}) {
  if (!paper) {
    return (
      <div className="text-sm text-base-content/40 leading-relaxed">
        Hover or click a node to see its abstract.
      </div>
    );
  }
  return (
    <>
      <div className="flex items-center gap-2 mb-2 text-[11px] uppercase tracking-wider font-medium text-base-content/50">
        {isPinned ? (
          <span className="text-primary font-semibold">pinned</span>
        ) : isClicked ? (
          <span className="text-accent font-semibold">clicked</span>
        ) : (
          <span className="font-mono">neighbor</span>
        )}
        {similarity !== undefined && similarity < 1 && (
          <span className="font-mono text-accent">
            sim = {similarity.toFixed(3)}
          </span>
        )}
        {paper.source && (
          <span className="ml-auto font-mono">{paper.source}</span>
        )}
        {paper.paper_date && (
          <span className="font-mono">{formatDate(paper.paper_date)}</span>
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
            {unicodify(paper.title)}
          </a>
        ) : (
          unicodify(paper.title)
        )}
      </h2>

      {paper.authors.length > 0 && (
        <p className="mt-2 text-xs text-base-content/60 leading-relaxed">
          {paper.authors.map(unicodify).join(", ")}
        </p>
      )}

      <p className="mt-1 text-[11px] text-base-content/30 font-mono">
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

      {paper.abstract ? (
        <p className="mt-3 text-sm text-base-content/80 whitespace-pre-wrap leading-relaxed">
          {unicodify(paper.abstract)}
        </p>
      ) : (
        <p className="mt-3 text-sm text-base-content/40 italic">
          No abstract available.
        </p>
      )}
    </>
  );
}

// "2026-01-16" → "Jan 2026". Returns the raw string on any parse failure.
function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-/.exec(iso);
  if (!m) return iso;
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const monthIdx = parseInt(m[2], 10) - 1;
  const monthName = months[monthIdx] ?? m[2];
  return `${monthName} ${m[1]}`;
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

// Standard short-form citation: "Cheng, 2025" or "Cheng et al., 2025".
// Falls back to a truncated title so a node never renders as an empty
// pill when paper_date or authors are missing (e.g. during a partial
// fetch or for older imports).
function formatCitation(paper: Paper | undefined): string {
  if (!paper) return "";
  const year = paper.paper_date ? paper.paper_date.slice(0, 4) : null;
  const firstAuthor = paper.authors?.[0];
  if (firstAuthor) {
    // Surname = last whitespace-separated token. Handles "Daizhan Cheng"
    // → "Cheng" and "Van Den Berg" → "Berg" (acceptable for v1).
    const cleaned = unicodify(firstAuthor);
    const surname = cleaned.trim().split(/\s+/).pop() ?? cleaned;
    const suffix = paper.authors.length > 1 ? " et al." : "";
    return year ? `${surname}${suffix}, ${year}` : `${surname}${suffix}`;
  }
  // No authors → fall back to title slice so the node still says something.
  const title = unicodify(paper.title ?? paper.paper_id);
  return title.length > 14 ? `${title.slice(0, 14)}…` : title;
}

// Greedy word-wrap into roughly square blocks. Splits on spaces and packs
// words into lines, starting a new line whenever the current line would
// exceed the target. Single words longer than the target stay on their
// own line (we never break inside a word). Returns at least one line for
// any non-empty input. Used to keep node-citation circles roughly round
// rather than ballooning horizontally for long surnames.
function wrapLabel(s: string, targetChars: number): string[] {
  const trimmed = s.trim();
  if (!trimmed) return [];
  const words = trimmed.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const w of words) {
    if (!current) {
      current = w;
      continue;
    }
    if (current.length + 1 + w.length <= targetChars) {
      current = `${current} ${w}`;
    } else {
      lines.push(current);
      current = w;
    }
  }
  if (current) lines.push(current);
  return lines;
}

// Map common TeX accent macros into the corresponding Unicode characters.
// Authors and titles arrive from the backend with raw TeX in them
// (e.g. "Yama\c{c}", "\'{e}", "Sch\"on") because BibTeX is lossy. We
// don't mutate the data model — this is applied at render time only.
//
// Strategy: rewrite each accent macro into "letter + combining diacritic"
// then NFC-normalize so precomposed glyphs win where they exist (most do).
// The combining-character approach handles every base letter without
// having to enumerate them.
//
// Accents covered (per the round-3 spec):
//   \c{x}          cedilla     U+0327
//   \'{x}, \'x     acute       U+0301
//   \`{x}, \`x     grave       U+0300
//   \^{x}, \^x     circumflex  U+0302
//   \"{x}, \"x     umlaut      U+0308
//   \~{x}, \~x     tilde       U+0303
//   \.x            dot above   U+0307
//   \={x}          macron      U+0304
//
// Plus fallback: strip a stray backslash before a letter so junk like
// "\foo" doesn't survive untouched.
const TEX_ACCENT: Record<string, string> = {
  c: "̧",
  "'": "́",
  "`": "̀",
  "^": "̂",
  '"': "̈",
  "~": "̃",
  ".": "̇",
  "=": "̄",
};
function unicodify(s: string): string {
  if (!s || s.indexOf("\\") < 0) return s;
  // Pattern matches both braced (\c{c}) and unbraced (\'e) forms.
  // Note the backslash is escaped twice here: once for the regex, once
  // for the JS string literal.
  const re = /\\([c'`^"~.=])(?:\{([A-Za-z])\}|([A-Za-z]))/g;
  let out = s.replace(re, (_m, accent: string, braced?: string, bare?: string) => {
    const letter = braced ?? bare;
    const combiner = TEX_ACCENT[accent];
    if (!letter || !combiner) return _m;
    return (letter + combiner).normalize("NFC");
  });
  // Fallback: strip standalone backslashes before a letter ("\foo" → "foo").
  // Skip already-handled accent macros (none should remain after the pass
  // above, but be defensive).
  out = out.replace(/\\([A-Za-z])/g, "$1");
  return out;
}

if (process.env.NODE_ENV !== "production") {
  // Tiny inline sanity asserts so a regression here trips on first load.
  console.assert(
    unicodify("Yama\\c{c}") === "Yamaç",
    "unicodify cedilla failed",
  );
  console.assert(
    unicodify("Sch\\\"on") === "Schön",
    "unicodify umlaut (unbraced) failed",
  );
  console.assert(
    unicodify("Andr\\'e") === "André",
    "unicodify acute (unbraced) failed",
  );
  console.assert(
    unicodify("plain text") === "plain text",
    "unicodify must be a no-op on plain text",
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
