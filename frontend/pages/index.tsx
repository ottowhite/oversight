import Head from "next/head";
import { useEffect, useMemo, useRef, useState } from "react";

type Paper = {
  paper_id: string;
  title: string;
  abstract: string;
  source?: string | null;
  link?: string | null;
  paper_date?: string | null;
};

const API_BASE = ""; // use Next.js rewrite to proxy to backend

const TIME_STEPS = [7, 14, 30, 90, 180, 365, 730, 1095, 1825, 2555, 3650];
const DEFAULT_TIME_INDEX = 7; // 1095 days = 3 years

const LIMIT_STEPS = [10, 15, 20, 25, 30, 40, 50];
const DEFAULT_LIMIT_INDEX = 0; // 10 results

export default function HomePage() {
  const [text, setText] = useState("");
  const [timeIndex, setTimeIndex] = useState<number>(DEFAULT_TIME_INDEX);
  const timeDays = TIME_STEPS[timeIndex];
  const [limitIndex, setLimitIndex] = useState<number>(DEFAULT_LIMIT_INDEX);
  const limit = LIMIT_STEPS[limitIndex];
  const [efSearch, setEfSearch] = useState<number>(50);

  // Exponential mapping for ef_search slider: position 0–100 maps to 10–500
  const EF_MIN = 10;
  const EF_MAX = 500;
  const efToSlider = (ef: number) =>
    Math.round((Math.log(ef / EF_MIN) / Math.log(EF_MAX / EF_MIN)) * 100);
  const sliderToEf = (pos: number) =>
    Math.round(EF_MIN * Math.pow(EF_MAX / EF_MIN, pos / 100));
  const [sources, setSources] = useState({
    arxiv: true,
    // AI conferences
    ICML: true,
    NeurIPS: true,
    ICLR: true,
    // Systems conferences
    OSDI: true,
    SOSP: true,
    ASPLOS: true,
    ATC: true,
    NSDI: true,
    MLSys: true,
    EuroSys: true,
    VLDB: true
  });
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [eyeSpinning, setEyeSpinning] = useState(false);
  const [systemsExpanded, setSystemsExpanded] = useState(false);
  const [aiExpanded, setAiExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const lastRequestIdRef = useRef<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Paper[]>([]);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Inventory state
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventory, setInventory] = useState<{
    conferences: Record<string, Record<number, number>>;
    counts: Record<string, number>;
    next_dates: Record<string, { date: string; passed: boolean }>;
  } | null>(null);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [inventoryOpen, setInventoryOpen] = useState(false);

  const timeLabel = useMemo(() => {
    if (timeDays >= 365) {
      const years = Math.round(timeDays / 365);
      return `${years} year${years === 1 ? "" : "s"}`;
    }
    if (timeDays >= 30) {
      const months = Math.round(timeDays / 30);
      return `${months} month${months === 1 ? "" : "s"}`;
    }
    return `${timeDays} day${timeDays === 1 ? "" : "s"}`;
  }, [timeDays]);

  // Scroll to bottom when results change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [results, loading]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    setResults([]);
    setSubmittedQuery(text);

    const reqId = Date.now();
    lastRequestIdRef.current = reqId;

    try {
      const resp = await fetch(`/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
        cache: "no-store",
        body: JSON.stringify({
          text,
          time_window_days: timeDays,
          limit,
          ef_search: efSearch,
          sources,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `Request failed: ${resp.status}`);
      if (lastRequestIdRef.current !== reqId) return; // a newer request finished; ignore this one
      setResults(data.results || []);
    } catch (err: any) {
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  // Conference categories
  const aiConferences = ['ICML', 'NeurIPS', 'ICLR'];
  const systemsConferences = ['OSDI', 'SOSP', 'ASPLOS', 'ATC', 'NSDI', 'MLSys', 'EuroSys', 'VLDB'];

  // Check if all conferences in a category are selected
  const isAllAISelected = aiConferences.every(conf => sources[conf as keyof typeof sources]);
  const isAllSystemsSelected = systemsConferences.every(conf => sources[conf as keyof typeof sources]);

  function toggleSource(key: keyof typeof sources) {
    setSources((s) => ({ ...s, [key]: !s[key] }));
  }

  function toggleAllAI() {
    const newValue = !isAllAISelected;
    setSources((s) => {
      const updated = { ...s };
      aiConferences.forEach(conf => {
        updated[conf as keyof typeof sources] = newValue;
      });
      return updated;
    });
  }

  function toggleAllSystems() {
    const newValue = !isAllSystemsSelected;
    setSources((s) => {
      const updated = { ...s };
      systemsConferences.forEach(conf => {
        updated[conf as keyof typeof sources] = newValue;
      });
      return updated;
    });
  }

  async function fetchInventory() {
    setInventoryOpen(true);
    setInventoryError(null);
    setInventoryLoading(true);
    try {
      const resp = await fetch(`/api/inventory`);
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.error || `Request failed: ${resp.status}`);
      setInventory(data);
    } catch (err: any) {
      setInventoryError(err.message || String(err));
    } finally {
      setInventoryLoading(false);
    }
  }

  function navigateToAbstract(abstract: string) {
    setText(abstract);
    // Trigger search automatically after setting the text
    setTimeout(() => {
      onSubmit(new Event('submit') as any);
    }, 100);
  }

  return (
    <>
    <Head>
      <title>Oversight</title>
      <style>{`
        @keyframes eye-spin-cw { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes eye-spin-ccw { from { transform: rotate(0deg); } to { transform: rotate(-360deg); } }
      `}</style>
    </Head>
    <main className="grid h-screen grid-rows-[auto,1fr]">
      {/* Header */}
      <header className="border-b border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <button
            onClick={() => {
              setSidebarOpen((v) => !v);
              setEyeSpinning(true);
            }}
            className="btn btn-ghost btn-sm btn-circle"
            title={sidebarOpen ? 'Hide filters' : 'Show filters'}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              className="h-8 w-8"
              onAnimationEnd={() => setEyeSpinning(false)}
              style={eyeSpinning ? { animation: `${sidebarOpen ? 'eye-spin-cw' : 'eye-spin-ccw'} 300ms ease-in-out` } : undefined}
            >
              {/* Material Design visibility (eye) icon */}
              <path
                d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"
                fill="currentColor"
              />
              {/* Pupil */}
              <circle cx="12" cy="12" r="3" fill="black" />
            </svg>
          </button>
          <h1 className="text-lg font-semibold">Oversight</h1>
          <a
            href="https://github.com/ottowhite/oversight"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-2 text-base text-base-content/60 transition-colors hover:text-base-content"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 16 16"
              fill="currentColor"
              className="h-7 w-7"
            >
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
            </svg>
            GitHub
          </a>
        </div>
      </header>

      {/* Main area: sidebar + chat */}
      <div
        className="mx-auto grid min-h-0 w-full max-w-6xl grid-cols-1 gap-4 px-4 py-4"
        style={{
          gridTemplateColumns: sidebarOpen ? '320px 1fr' : '0px 1fr',
          transition: 'grid-template-columns 200ms ease-in-out',
        }}
      >
        {/* Sidebar / Controls */}
        <aside
          className="card bg-base-200 shadow-sm overflow-y-auto overflow-x-hidden min-w-0 min-h-0"
          style={{
            opacity: sidebarOpen ? 1 : 0,
            transition: 'opacity 150ms ease-in-out',
          }}
        >
          <div className="card-body gap-4">
            <h2 className="card-title text-base">Filters</h2>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Lookback window</span>
                <span className="label-text-alt text-primary font-medium">{timeLabel}</span>
              </label>
              <input
                type="range"
                min={0}
                max={TIME_STEPS.length - 1}
                step={1}
                value={timeIndex}
                onChange={(e) => setTimeIndex(parseInt((e.target as HTMLInputElement).value, 10))}
                className="range range-primary"
              />
              <div className="flex justify-between px-2 text-xs opacity-60">
                <span>1w</span>
                <span>3m</span>
                <span>1y</span>
                <span>5y</span>
                <span>10y</span>
              </div>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Max results</span>
                <span className="label-text-alt text-primary font-medium">{limit}</span>
              </label>
              <input
                type="range"
                min={0}
                max={LIMIT_STEPS.length - 1}
                step={1}
                value={limitIndex}
                onChange={(e) => setLimitIndex(parseInt((e.target as HTMLInputElement).value, 10))}
                className="range range-primary"
              />
              <div className="flex justify-between px-2 text-xs opacity-60">
                <span>10</span>
                <span>20</span>
                <span>30</span>
                <span>50</span>
              </div>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Search precision (ef_search)</span>
                <span className="label-text-alt text-primary font-medium">{efSearch}</span>
              </label>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={efToSlider(efSearch)}
                onChange={(e) => setEfSearch(sliderToEf(parseInt((e.target as HTMLInputElement).value, 10)))}
                className="range range-primary"
              />
              <div className="flex justify-between px-2 text-xs opacity-60">
                <span>10</span>
                <span>50</span>
                <span>200</span>
                <span>500</span>
              </div>
            </div>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Sources</span>
                <button
                  type="button"
                  onClick={fetchInventory}
                  className="label-text-alt underline opacity-50 hover:opacity-70 transition-opacity cursor-pointer"
                >
                  show all
                </button>
              </label>

              {/* Systems conferences */}
              <div>
                <label className="label cursor-pointer justify-start gap-3 py-2">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={isAllSystemsSelected}
                    onChange={toggleAllSystems}
                    ref={(el) => {
                      if (el) {
                        el.indeterminate = systemsConferences.some(conf => sources[conf as keyof typeof sources]) && !isAllSystemsSelected;
                      }
                    }}
                  />
                  <span className="label-text font-medium flex-1">Systems conferences</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs btn-circle"
                    onClick={() => setSystemsExpanded((v) => !v)}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className={`h-4 w-4 transition-transform duration-150 ${systemsExpanded ? 'rotate-180' : ''}`}>
                      <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                    </svg>
                  </button>
                </label>
                {systemsExpanded && systemsConferences.map(conf => (
                  <label key={conf} className="label cursor-pointer justify-start gap-3 py-1 ml-6">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={sources[conf as keyof typeof sources]}
                      onChange={() => toggleSource(conf as keyof typeof sources)}
                    />
                    <span className="label-text text-sm">{conf}</span>
                  </label>
                ))}
              </div>

              {/* AI conferences */}
              <div>
                <label className="label cursor-pointer justify-start gap-3 py-2">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={isAllAISelected}
                    onChange={toggleAllAI}
                    ref={(el) => {
                      if (el) {
                        el.indeterminate = aiConferences.some(conf => sources[conf as keyof typeof sources]) && !isAllAISelected;
                      }
                    }}
                  />
                  <span className="label-text font-medium flex-1">AI conferences</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs btn-circle"
                    onClick={() => setAiExpanded((v) => !v)}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className={`h-4 w-4 transition-transform duration-150 ${aiExpanded ? 'rotate-180' : ''}`}>
                      <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                    </svg>
                  </button>
                </label>
                {aiExpanded && aiConferences.map(conf => (
                  <label key={conf} className="label cursor-pointer justify-start gap-3 py-1 ml-6">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={sources[conf as keyof typeof sources]}
                      onChange={() => toggleSource(conf as keyof typeof sources)}
                    />
                    <span className="label-text text-sm">{conf}</span>
                  </label>
                ))}
              </div>

              {/* arXiv */}
              <label className="label cursor-pointer justify-start gap-3 py-2">
                <input type="checkbox" className="checkbox checkbox-sm" checked={sources.arxiv} onChange={() => toggleSource("arxiv")} />
                <span className="label-text">arXiv</span>
              </label>
            </div>

          </div>
        </aside>

        {/* Chat-like panel */}
        <section className="card bg-base-200 shadow-sm overflow-hidden min-h-0 flex flex-col">
          {/* Messages area */}
          <div className="flex-1 min-h-0 overflow-y-auto p-4 flex flex-col gap-4">
            {/* Empty state */}
            {results.length === 0 && !loading && !submittedQuery && (
              <div className="flex-1 flex items-center justify-center">
                <p className="text-base-content/40 text-lg">Search for papers below</p>
              </div>
            )}

            {/* Submitted query as sent message */}
            {submittedQuery && (
              <div className="flex justify-end">
                <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-primary text-primary-content px-4 py-3">
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{submittedQuery}</p>
                </div>
              </div>
            )}

            {/* Loading indicator */}
            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm bg-base-300 px-4 py-3">
                  <span className="loading loading-dots loading-sm"></span>
                </div>
              </div>
            )}

            {/* Results as received messages */}
            {results.map((p) => (
              <div key={p.paper_id} className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-base-300 text-base-content px-4 py-3">
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <h3 className="font-semibold text-sm">{p.title}</h3>
                    <small className="text-xs opacity-60 whitespace-nowrap shrink-0">
                      {p.source || ''}
                      {p.paper_date ? ` · ${new Date(p.paper_date).toLocaleDateString()}` : ''}
                    </small>
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed opacity-80">{p.abstract}</p>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => navigateToAbstract(p.abstract)}
                      className="btn btn-xs btn-ghost text-primary hover:bg-primary/10"
                    >
                      Find Similar
                    </button>
                    {p.link && (
                      <a
                        className="btn btn-xs btn-ghost text-primary hover:bg-primary/10"
                        href={p.link}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View Paper
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {/* No results message */}
            {results.length === 0 && !loading && submittedQuery && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm bg-base-300 text-base-content/60 px-4 py-3 text-sm">
                  No results found. Try a different query.
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input bar at the bottom */}
          <div className="border-t border-base-300/60 p-3">
            {error && <div className="alert alert-error py-2 text-sm mb-2">{error}</div>}
            <form onSubmit={onSubmit} className="flex items-end gap-2">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (text.trim() && !loading) {
                      onSubmit(e as any);
                    }
                  }
                }}
                rows={1}
                placeholder="Search for papers..."
                className="textarea textarea-bordered flex-1 min-h-[2.5rem] max-h-32 resize-none text-sm leading-relaxed"
                style={{ fieldSizing: 'content' } as any}
                required
              />
              <button
                type="submit"
                className={`btn btn-primary btn-circle btn-sm ${loading ? 'btn-disabled' : ''}`}
                disabled={loading || !text.trim()}
                title="Send"
              >
                {loading ? (
                  <span className="loading loading-spinner loading-xs"></span>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                    <path d="M3.105 2.29a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.897 28.897 0 0015.293-7.155.75.75 0 000-1.114A28.897 28.897 0 003.105 2.289z" />
                  </svg>
                )}
              </button>
            </form>
          </div>
        </section>
      </div>

      {/* Inventory modal */}
      {inventoryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="relative flex flex-col bg-base-200 rounded-xl shadow-2xl" style={{ width: '75vw', height: '75vh' }}>
            {/* Header with close button */}
            <div className="flex items-center justify-between border-b border-base-300 px-6 py-4">
              <h2 className="text-lg font-semibold">Database Inventory</h2>
              <button
                onClick={() => setInventoryOpen(false)}
                className="btn btn-sm btn-circle btn-ghost"
              >
                X
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6">
              {inventoryLoading && (
                <div className="flex items-center justify-center h-full">
                  <span className="loading loading-spinner loading-lg"></span>
                </div>
              )}
              {inventoryError && (
                <div className="alert alert-error">{inventoryError}</div>
              )}
              {inventory && !inventoryLoading && (() => {
                // Compute the full year range, extending to at least the current year
                const currentYear = new Date().getFullYear();
                const allYears = Object.values(inventory.conferences).flatMap(m => Object.keys(m).map(Number));
                const minYear = Math.min(...allYears);
                const maxYear = Math.max(...allYears, currentYear);
                const yearColumns: number[] = [];
                for (let y = minYear; y <= maxYear; y++) yearColumns.push(y);

                // Fixed display order: systems, AI, then arxiv
                const SOURCE_ORDER = [
                  'OSDI', 'SOSP', 'ASPLOS', 'ATC', 'NSDI', 'EuroSys', 'VLDB',
                  'ICML', 'NeurIPS', 'ICLR', 'MLSys',
                  'arxiv',
                ];
                const knownSources = new Set(SOURCE_ORDER);
                const sources = [
                  ...SOURCE_ORDER.filter(s => s in inventory.conferences || s in inventory.counts),
                  ...Object.keys(inventory.conferences).filter(s => !knownSources.has(s)),
                ];

                return (
                  <>
                    <div className="text-xl font-medium mb-4">
                      Total papers: {inventory.counts.total?.toLocaleString() ?? '—'}
                    </div>
                    <div className="overflow-x-auto">
                      <table className="table table-zebra w-full">
                        <thead>
                          <tr>
                            <th className="sticky left-0 bg-base-200 z-10">Source</th>
                            <th>Papers</th>
                            <th className="text-center">Missing</th>
                            <th className="text-center">Predicted Next</th>
                            {yearColumns.map(y => (
                              <th key={y} className="text-center">{y}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {sources.map(source => {
                            const yearCounts = inventory.conferences[source] ?? {};
                            const isArxiv = source === 'arxiv';
                            return (
                              <tr key={source}>
                                <td className="font-mono text-base sticky left-0 bg-base-200 z-10">{source}</td>
                                <td>{inventory.counts[source]?.toLocaleString() ?? '—'}</td>
                                <td className="text-center whitespace-nowrap">
                                  {(() => {
                                    if (isArxiv) return <span className="opacity-30">—</span>;
                                    const nd = inventory.next_dates[source];
                                    const missing = yearColumns.filter(y => {
                                      if (y < 2020) return false;
                                      const isFuture = nd && y >= new Date(nd.date).getFullYear();
                                      return !isFuture && yearCounts[y] == null;
                                    });
                                    if (missing.length === 0) return <span className="text-success">0</span>;
                                    return <span className="text-error font-bold">{missing.join(', ')}</span>;
                                  })()}
                                </td>
                                <td className="text-center whitespace-nowrap">
                                  {(() => {
                                    const nd = inventory.next_dates[source];
                                    if (!nd) return <span className="opacity-30">—</span>;
                                    return nd.passed
                                      ? <span className="text-error font-bold">&#10007; {nd.date}</span>
                                      : <span className="text-success">{nd.date}</span>;
                                  })()}
                                </td>
                                {yearColumns.map(y => {
                                  const count = yearCounts[y];
                                  const nd = inventory.next_dates[source];
                                  const isFuture = nd && y >= new Date(nd.date).getFullYear();
                                  return (
                                    <td key={y} className="text-center whitespace-nowrap">
                                      {isArxiv
                                        ? (count != null
                                          ? <span>({count.toLocaleString()})</span>
                                          : <span className="opacity-30">—</span>)
                                        : count != null
                                          ? <span className="text-success font-bold">&#10003; ({count})</span>
                                          : isFuture
                                            ? <span className="opacity-50">&#8230;</span>
                                            : <span className="text-error font-bold">&#10007;</span>
                                      }
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </main>
    </>
  );
}
