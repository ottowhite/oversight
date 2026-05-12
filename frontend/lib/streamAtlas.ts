// streamAtlas — pure (no React) helper for reading the NDJSON atlas
// endpoint and progressively feeding points to the renderer.
//
// Wire format (frozen contract with the backend at /api/atlas?format=ndjson):
//   Content-Type: application/x-ndjson
//   Line 1 (header):
//     {"projection": "pacmap_v1", "total": 524604,
//      "bbox": [xmin, ymin, xmax, ymax]}
//   Line 2..N (one point per line):
//     {"paper_id": "1304.5893", "title": "...",
//      "source": "arxiv", "x": 0.41, "y": 3.33}
//
// Chunks from `getReader()` arrive at arbitrary byte boundaries, so we
// buffer the trailing partial line between reads and split on '\n' up
// to the last newline; the leftover tail is carried into the next chunk.
// The first non-empty line is the header (parsed + delivered via
// onHeader). Subsequent lines accumulate into a `batch` array and are
// flushed via onBatch every BATCH_SIZE points, plus once more at end.

export type AtlasPoint = {
  paper_id: string;
  title: string;
  source: string | null;
  x: number;
  y: number;
};

export type AtlasHeader = {
  projection: string;
  total: number;
  bbox: [number, number, number, number];
};

// Tuned to match the in-page redraw cadence: 25k points is small enough
// that the first batch lights up the canvas quickly, large enough to
// keep the per-batch overhead (state update + GL upload) amortised.
// Smaller values starve the renderer — batches arrive faster than
// scatter.draw can complete, so the canvas stays blank until the stream
// ends and the final coalesced draw fires.
const BATCH_SIZE = 25000;

export async function streamAtlas(
  projection: string,
  signal: AbortSignal,
  onHeader: (h: AtlasHeader) => void,
  onBatch: (batch: AtlasPoint[]) => void,
): Promise<void> {
  const resp = await fetch(
    `/api/atlas?projection=${encodeURIComponent(projection)}&format=ndjson`,
    { signal },
  );
  if (!resp.ok || !resp.body) {
    throw new Error(`atlas stream failed (${resp.status})`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let headerSeen = false;
  let batch: AtlasPoint[] = [];

  // Single-line dispatch. Skips blank lines, routes the first non-empty
  // one to onHeader, everything after to the batch buffer.
  const handleLine = (line: string) => {
    if (line.length === 0) return;
    if (!headerSeen) {
      const header = JSON.parse(line) as AtlasHeader;
      onHeader(header);
      headerSeen = true;
      return;
    }
    const point = JSON.parse(line) as AtlasPoint;
    batch.push(point);
    if (batch.length >= BATCH_SIZE) {
      onBatch(batch);
      batch = [];
    }
  };

  // Read loop. AbortError from the underlying fetch/reader propagates
  // naturally; we only need to make sure we don't swallow it.
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // Split only up to the last '\n' — everything after stays buffered
    // because it may be a mid-line fragment.
    const lastNl = buf.lastIndexOf("\n");
    if (lastNl < 0) continue;
    const chunk = buf.slice(0, lastNl);
    buf = buf.slice(lastNl + 1);
    // Avoid an empty-string split-emit when the chunk ends on '\n\n'
    // or starts cleanly at a newline by filtering inside handleLine.
    const lines = chunk.split("\n");
    for (const line of lines) handleLine(line);
  }

  // Flush any decoder state and the trailing partial line. The server
  // may or may not send a final '\n'; tolerate both.
  buf += decoder.decode();
  if (buf.length > 0) {
    // Defensive: only parse if it looks like a complete JSON object —
    // a truncated final line is dropped silently rather than crashing
    // the stream. The backend always terminates lines with '\n' so this
    // branch is just belt-and-braces.
    const trimmed = buf.trim();
    if (trimmed.length > 0) {
      try {
        handleLine(trimmed);
      } catch {
        /* swallow trailing-garbage parse errors only */
      }
    }
  }

  // Final partial batch (may be smaller than BATCH_SIZE).
  if (batch.length > 0) {
    onBatch(batch);
    batch = [];
  }
}

// Bbox-derived equivalent of the in-page normalizePoints. The caller
// passes the header.bbox once and gets back a per-point closure so
// each point lands in the renderer's [-1, 1] device-coord space without
// a global min/max scan over the whole corpus (the streaming case can't
// afford to wait for all points before starting to draw). Math kept
// pixel-identical to the original: aspect-preserving span, 1.8 margin.
export function makeNormalizer(
  bbox: [number, number, number, number],
): (p: AtlasPoint) => [number, number] {
  const [xmin, ymin, xmax, ymax] = bbox;
  const span = Math.max(xmax - xmin, ymax - ymin) || 1;
  const cx = (xmin + xmax) / 2;
  const cy = (ymin + ymax) / 2;
  const scale = 1.8 / span;
  return (p) => [(p.x - cx) * scale, (p.y - cy) * scale];
}
