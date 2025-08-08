import { useMemo, useRef, useState } from "react";

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
  const [sources, setSources] = useState<{ arxiv: boolean; ai: boolean; systems: boolean }>(
    { arxiv: true, ai: true, systems: true }
  );
  const [loading, setLoading] = useState(false);
  const lastRequestIdRef = useRef<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Paper[]>([]);

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

  function toggleSource(key: keyof typeof sources) {
    setSources((s) => ({ ...s, [key]: !s[key] }));
  }

  return (
    <main className="grid h-screen grid-rows-[auto,1fr]">
      {/* Header */}
      <header className="border-b border-base-300/60 bg-base-100/60 backdrop-blur supports-[backdrop-filter]:bg-base-100/40">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <div className="avatar placeholder">
            <div className="w-8 rounded bg-primary text-primary-content">
              <span className="text-sm font-bold">PS</span>
            </div>
          </div>
          <h1 className="text-lg font-semibold">Paper Search</h1>
          <span className="ml-auto text-xs text-base-content/60">Embeddings-backed search</span>
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
                <span className="label-text">Sources</span>
              </label>
              <label className="label cursor-pointer justify-start gap-3">
                <input type="checkbox" className="checkbox checkbox-sm" checked={sources.arxiv} onChange={() => toggleSource("arxiv")} />
                <span className="label-text">arXiv</span>
              </label>
              <label className="label cursor-pointer justify-start gap-3">
                <input type="checkbox" className="checkbox checkbox-sm" checked={sources.ai} onChange={() => toggleSource("ai")} />
                <span className="label-text">AI conferences</span>
              </label>
              <label className="label cursor-pointer justify-start gap-3">
                <input type="checkbox" className="checkbox checkbox-sm" checked={sources.systems} onChange={() => toggleSource("systems")} />
                <span className="label-text">Systems conferences</span>
              </label>
            </div>

            <button onClick={onSubmit as any} className={`btn btn-primary ${loading ? 'btn-disabled loading' : ''}`} disabled={loading}>
              {loading ? 'Searching…' : 'Search'}
            </button>
            {error && <div className="alert alert-error py-2 text-sm">{error}</div>}
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
                      placeholder="Paste related abstract(s) here..."
                      className="textarea textarea-bordered textarea-primary w-full text-base-content placeholder:text-base-content/60"
                      required
                    />
                    <div className="flex items-center justify-between">
                      <span className="text-xs opacity-70">The backend wraps the repository and queries Postgres using embeddings.</span>
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
                    {p.link && (
                      <a className="link link-primary mt-2 inline-block" href={p.link} target="_blank" rel="noreferrer">View paper</a>
                    )}
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
    </main>
  );
}
