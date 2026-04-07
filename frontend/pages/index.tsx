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

export default function HomePage() {
  const [text, setText] = useState("");
  const [timeDays, setTimeDays] = useState<number>(365 * 5);
  const [limit, setLimit] = useState<number>(10);
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
  const [loading, setLoading] = useState(false);
  const lastRequestIdRef = useRef<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Paper[]>([]);

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

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    setResults([]);

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
    </Head>
    <main className="grid h-screen grid-rows-[auto,1fr]">
      {/* Header */}
      <header className="border-b border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <div className="avatar placeholder">
            <div className="w-8 rounded bg-primary text-primary-content">
              <span className="text-sm font-bold">O</span>
            </div>
          </div>
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
      <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-4 px-4 py-4 md:grid-cols-[320px,1fr]">
        {/* Sidebar / Controls */}
        <aside className="card bg-base-200 shadow-sm">
          <div className="card-body gap-4">
            <h2 className="card-title text-base">Filters</h2>

            <div className="form-control">
              <label className="label">
                <span className="label-text">Lookback window</span>
                <span className="label-text-alt text-primary font-medium">{timeLabel}</span>
              </label>
              <input
                type="range"
                min={7}
                max={3650}
                step={1}
                value={timeDays}
                onChange={(e) => setTimeDays(parseInt((e.target as HTMLInputElement).value, 10))}
                className="range range-primary"
              />
              <div className="flex justify-between px-2 text-xs opacity-60">
                <span>1w</span>
                <span>1m</span>
                <span>1y</span>
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
                min={1}
                max={100}
                step={1}
                value={limit}
                onChange={(e) => setLimit(parseInt((e.target as HTMLInputElement).value, 10))}
                className="range range-primary"
              />
              <div className="flex justify-between px-2 text-xs opacity-60">
                <span>1</span>
                <span>25</span>
                <span>50</span>
                <span>100</span>
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
              </label>

              {/* arXiv */}
              <label className="label cursor-pointer justify-start gap-3">
                <input type="checkbox" className="checkbox checkbox-sm" checked={sources.arxiv} onChange={() => toggleSource("arxiv")} />
                <span className="label-text">arXiv</span>
              </label>

              {/* AI conferences */}
              <label className="label cursor-pointer justify-start gap-3">
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
                <span className="label-text font-medium">AI conferences</span>
              </label>
              {aiConferences.map(conf => (
                <label key={conf} className="label cursor-pointer justify-start gap-3 ml-6">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={sources[conf as keyof typeof sources]}
                    onChange={() => toggleSource(conf as keyof typeof sources)}
                  />
                  <span className="label-text text-sm">{conf}</span>
                </label>
              ))}

              {/* Systems conferences */}
              <label className="label cursor-pointer justify-start gap-3">
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
                <span className="label-text font-medium">Systems conferences</span>
              </label>
              {systemsConferences.map(conf => (
                <label key={conf} className="label cursor-pointer justify-start gap-3 ml-6">
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

            <button onClick={onSubmit as any} className={`btn btn-primary ${loading ? 'btn-disabled loading' : ''}`} disabled={loading}>
              {loading ? 'Searching…' : 'Search'}
            </button>
            {error && <div className="alert alert-error py-2 text-sm">{error}</div>}

            <div className="divider my-1"></div>

            <button
              onClick={fetchInventory}
              className={`btn btn-outline btn-secondary btn-sm`}
            >
              Database Inventory
            </button>
          </div>
        </aside>

        {/* Chat-like panel */}
        <section className="card bg-base-200 shadow-sm overflow-hidden">
          <div className="card-body p-0">
            {/* Messages area */}
            <div className="flex h-[calc(100vh-200px)] flex-col gap-4 overflow-y-auto p-4">
              {/* User input bubble */}
              <div className="chat chat-end">
                <div className="chat-bubble chat-bubble-primary w-full max-w-3xl">
                  <form onSubmit={onSubmit} className="flex flex-col gap-2">
                    <textarea
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      rows={6}
                      placeholder="Enter arbitrary search queries, abstracts, ideas or text snippets here..."
                      className="textarea textarea-bordered textarea-primary w-full text-base-content placeholder:text-base-content/60"
                      required
                    />
                    <div className="flex items-center justify-between">
                      <button type="submit" className={`btn btn-sm btn-primary ${loading ? 'btn-disabled loading' : ''}`} disabled={loading}>
                        {loading ? 'Searching…' : 'Search'}
                      </button>
                    </div>
                  </form>
                </div>
              </div>

              {/* Results as assistant responses */}
              {results.map((p) => (
                <div key={p.paper_id} className="chat chat-start">
                  <div className="w-full max-w-3xl rounded-2xl bg-gray-700 text-gray-100 p-4">
                    <div className="mb-2 flex items-baseline justify-between gap-3">
                      <h3 className="font-semibold">{p.title}</h3>
                      <small className="opacity-70">
                        {p.source || ''}
                        {p.paper_date ? ` • ${new Date(p.paper_date).toLocaleDateString()}` : ''}
                      </small>
                    </div>
                    <p className="whitespace-pre-wrap leading-relaxed">{p.abstract}</p>
                    <div className="flex gap-3 mt-2">
                      <button
                        onClick={() => navigateToAbstract(p.abstract)}
                        className="btn btn-sm btn-outline btn-primary"
                      >
                        Find Similar
                      </button>
                      {p.link && (
                        <a
                          className="btn btn-sm btn-outline btn-primary"
                          href={p.link}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View paper
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}

              {results.length === 0 && !loading && (
                <div className="chat chat-start">
                  <div className="chat-bubble w-full max-w-3xl bg-base-100 text-base-content opacity-70">
                    No results yet. Submit a query above.
                  </div>
                </div>
              )}
            </div>
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
                // Compute the full year range across all conferences
                const allYears = Object.values(inventory.conferences).flatMap(m => Object.keys(m).map(Number));
                const minYear = Math.min(...allYears);
                const maxYear = Math.max(...allYears);
                const yearColumns: number[] = [];
                for (let y = minYear; y <= maxYear; y++) yearColumns.push(y);

                // Build rows: conferences first, then arxiv
                const sources = Object.keys(inventory.conferences);
                if (inventory.counts.arxiv != null && !sources.includes('arxiv')) {
                  sources.push('arxiv');
                }

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
                            <th className="text-center">Next Conference</th>
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
                                    const nd = inventory.next_dates[source];
                                    if (!nd) return <span className="opacity-30">—</span>;
                                    return nd.passed
                                      ? <span className="text-error font-bold">&#10007; {nd.date}</span>
                                      : <span className="text-success">{nd.date}</span>;
                                  })()}
                                </td>
                                {yearColumns.map(y => {
                                  const count = yearCounts[y];
                                  return (
                                    <td key={y} className="text-center whitespace-nowrap">
                                      {isArxiv
                                        ? <span className="opacity-30">—</span>
                                        : count != null
                                          ? <span className="text-success font-bold">&#10003; ({count})</span>
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
