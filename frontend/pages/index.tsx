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
    <main style={{ maxWidth: 960, margin: "0 auto", padding: 24 }}>
      <h1 style={{ marginBottom: 8 }}>Paper Search</h1>
      <p style={{ marginTop: 0, color: "#666" }}>
        Enter one or more related abstracts. The backend wraps the existing repository and queries Postgres using embeddings.
      </p>

      <form onSubmit={onSubmit} style={{ display: "grid", gap: 16 }}>
        <label style={{ display: "grid", gap: 8 }}>
          <span>Related abstracts</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            placeholder="Paste related abstract(s) here..."
            style={{ width: "100%", padding: 12, fontFamily: "inherit", fontSize: 14 }}
            required
          />
        </label>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <label style={{ display: "grid", gap: 4, flex: 1 }}>
            <span>Lookback window: {timeLabel}</span>
            <input
              type="range"
              min={7}
              max={3650}
              step={1}
              value={timeDays}
              onChange={(e) => setTimeDays(parseInt((e.target as HTMLInputElement).value, 10))}
            />
          </label>
          <div style={{ display: "flex", gap: 16 }}>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={sources.arxiv} onChange={() => toggleSource("arxiv")} />
              arXiv
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={sources.ai} onChange={() => toggleSource("ai")} />
              AI conferences
            </label>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={sources.systems} onChange={() => toggleSource("systems")} />
              Systems conferences
            </label>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12 }}>
          <button type="submit" disabled={loading} style={{ padding: "8px 14px" }}>
            {loading ? "Searching…" : "Search"}
          </button>
          {error && <span style={{ color: "red" }}>{error}</span>}
        </div>
      </form>

      <section style={{ marginTop: 24, display: "grid", gap: 16 }}>
        {results.map((p) => (
          <article key={p.paper_id} style={{ border: "1px solid #e5e7eb", padding: 16, borderRadius: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
              <h3 style={{ margin: 0 }}>{p.title}</h3>
              <small style={{ color: "#666" }}>
                {p.source || ""}
                {p.paper_date ? ` • ${new Date(p.paper_date).toLocaleDateString()}` : ""}
              </small>
            </div>
            <p style={{ whiteSpace: "pre-wrap" }}>{p.abstract}</p>
            {p.link && (
              <a href={p.link} target="_blank" rel="noreferrer">View</a>
            )}
          </article>
        ))}
        {results.length === 0 && !loading && (
          <p style={{ color: "#666" }}>No results yet. Submit a query above.</p>
        )}
      </section>
    </main>
  );
}
