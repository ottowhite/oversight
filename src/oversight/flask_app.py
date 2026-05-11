from __future__ import annotations

from datetime import date, timedelta
import os
import threading
from typing import Any

import psycopg
from flask import Flask, request
from flask_cors import CORS
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg import sql

from .Paper import Paper
from .PaperDatabase import PaperDatabase
from .PaperRepository import PaperRepository
from .ArXivRepository import ArXivRepository
from .ResearchListener import research_listener_group

# Load environment variables early so repo/db can connect
load_dotenv()

app = Flask(__name__)
# Allow local Next.js dev server by default; can be customized with CORS_ORIGINS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
CORS(app, resources={r"/api/*": {"origins": cors_origins}})


_neighbors_conn_lock = threading.Lock()
_neighbors_conn: psycopg.Connection[tuple[Any, ...]] | None = None

# Process-local cache for the similarity-distribution endpoint. Sampling 10K
# random embedding pairs takes ~hundreds of ms; the result is stable for the
# lifetime of the process under normal ingestion volume.
_similarity_distribution_lock = threading.Lock()
_similarity_distribution_cache: dict[str, float] | None = None
_similarity_distribution_sample_size = 10_000


def _get_neighbors_connection() -> psycopg.Connection[tuple[Any, ...]]:
    """Return a process-local pgvector-registered connection.

    The neighbors endpoint is read-only and latency-sensitive (target p95 30ms),
    so we amortize the ~25ms connect + ``register_vector`` cost across requests
    by reusing one connection per worker. Threaded WSGI servers serialize
    access through the lock; for higher concurrency, swap in psycopg_pool.
    """
    global _neighbors_conn
    if _neighbors_conn is None or _neighbors_conn.closed:
        database_url = os.getenv("DATABASE_URL")
        assert database_url is not None, "Database URL is not set"
        _neighbors_conn = psycopg.connect(database_url, autocommit=True)
        register_vector(_neighbors_conn)
    return _neighbors_conn


@app.get("/api/health")
def health() -> tuple[dict[str, str], int]:
    return {"status": "ok"}, 200


def _build_filters(
    repo: PaperRepository, sources_flags: dict[str, bool]
) -> list[sql.Composable]:
    filters: list[sql.Composable] = []

    # Collect individual sources
    selected_sources: list[str] = []

    # Handle arXiv
    if sources_flags.get("arxiv", False):
        selected_sources.append("arxiv")

    # Handle individual AI conferences
    ai_conferences = ["ICML", "NeurIPS", "ICLR"]
    for conf in ai_conferences:
        if sources_flags.get(conf, False):
            selected_sources.append(conf)

    # Handle individual Systems conferences
    systems_conferences = [
        "OSDI",
        "SOSP",
        "ASPLOS",
        "ATC",
        "NSDI",
        "MLSys",
        "EuroSys",
        "VLDB",
    ]
    for conf in systems_conferences:
        if sources_flags.get(conf, False):
            selected_sources.append(conf)

    # Build filter from selected sources
    if selected_sources:
        filters.append(repo.build_filter_sql(selected_sources))
    else:
        # If nothing selected, default to everything
        filters.append(
            repo.build_filter_sql(
                [
                    "arxiv",
                    "ICML",
                    "NeurIPS",
                    "ICLR",
                    "OSDI",
                    "SOSP",
                    "ASPLOS",
                    "ATC",
                    "NSDI",
                    "MLSys",
                    "EuroSys",
                    "VLDB",
                ]
            )
        )

    return filters


@app.post("/api/search")
@app.get("/api/search")
def search() -> tuple[dict[str, Any], int]:
    body: dict[str, Any] = request.get_json(silent=True) or {}
    # Support query params for GET as well
    if request.method == "GET" and not body:
        # Create sources dict from individual conference params
        sources: dict[str, bool] = {
            "arxiv": request.args.get("arxiv", "false").lower() == "true",
        }

        # Add individual AI conferences
        ai_conferences = ["ICML", "NeurIPS", "ICLR"]
        for conf in ai_conferences:
            sources[conf] = request.args.get(conf, "false").lower() == "true"

        # Add individual Systems conferences
        systems_conferences = [
            "OSDI",
            "SOSP",
            "ASPLOS",
            "ATC",
            "NSDI",
            "MLSys",
            "EuroSys",
            "VLDB",
        ]
        for conf in systems_conferences:
            sources[conf] = request.args.get(conf, "false").lower() == "true"

        body = {
            "text": request.args.get("text", ""),
            "time_window_days": request.args.get("time_window_days"),
            "sources": sources,
        }

    query_text_raw: Any = body.get("text", "")
    assert isinstance(query_text_raw, str), "text must be a string"
    query_text: str = query_text_raw.strip()
    if not query_text:
        return {"error": "text is required"}, 400

    time_window_days = body.get("time_window_days")
    try:
        time_window_days_int = (
            int(time_window_days) if time_window_days is not None else 365 * 5
        )
    except Exception:
        return {"error": "time_window_days must be an integer"}, 400

    limit = body.get("limit")
    try:
        limit_int = int(limit) if limit is not None else 10
        limit_int = max(1, min(100, limit_int))
    except Exception:
        return {"error": "limit must be an integer between 1 and 100"}, 400

    ef_search = body.get("ef_search")
    try:
        ef_search_int = int(ef_search) if ef_search is not None else 50
        ef_search_int = max(10, min(500, ef_search_int))
    except Exception:
        return {"error": "ef_search must be an integer between 10 and 500"}, 400

    sources_flags: dict[str, bool] = body.get("sources") or {}

    # Use repository in a context so connections are properly managed
    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        filters = _build_filters(repo, sources_flags)
        papers = repo.get_newest_related_papers(
            query_text,
            timedelta(days=time_window_days_int),
            filters,
            limit=limit_int,
            ef_search=ef_search_int,
        )

    results = []
    for p in papers:
        results.append(
            {
                "paper_id": p.paper_id,
                "title": p.title,
                "abstract": p.abstract,
                "source": p.source,
                "link": p.link,
                "authors": p.authors,
                "institutions": p.institutions,
                # paper_date is a datetime.date or datetime; convert to ISO string
                "paper_date": p.paper_date.isoformat()
                if hasattr(p.paper_date, "isoformat")
                else str(p.paper_date),
            }
        )

    return {"results": results}, 200


def _serialize_paper(paper: Any, similarity: float | None = None) -> dict[str, Any]:
    """Serialize a Paper object for JSON responses."""
    out: dict[str, Any] = {
        "paper_id": paper.paper_id,
        "title": paper.title,
        "abstract": paper.abstract,
        "source": paper.source,
        "link": paper.link,
        "authors": paper.authors,
        "institutions": paper.institutions,
        "paper_date": paper.paper_date.isoformat()
        if hasattr(paper.paper_date, "isoformat")
        else str(paper.paper_date),
    }
    if similarity is not None:
        out["similarity"] = similarity
    return out


@app.get("/api/papers/<paper_id>/neighbors")
def paper_neighbors(paper_id: str) -> tuple[dict[str, Any], int]:
    """Return the seed paper and its similarity-graph neighbors.

    Query params:
      k       int in [1, 50] (default 20)
      mutual  bool (default false). When true, restrict to mutual-kNN edges.
    """
    k_raw = request.args.get("k", "20")
    try:
        k = int(k_raw)
    except (TypeError, ValueError):
        return {"error": "k must be an integer"}, 400
    if k < 1 or k > 50:
        return {"error": "k must be between 1 and 50"}, 400

    mutual_raw = request.args.get("mutual", "false").strip().lower()
    if mutual_raw not in {"true", "false", "1", "0", "yes", "no"}:
        return {"error": "mutual must be a boolean"}, 400
    mutual = mutual_raw in {"true", "1", "yes"}

    # Skip the PaperRepository wrapper here: this endpoint does no embedding
    # work (the seed embedding is fetched from the DB), so loading the Google
    # client per request would only add latency. Reuse a process-local
    # connection so we don't pay 15-25ms of connect + register_vector per call.
    with _neighbors_conn_lock:
        con = _get_neighbors_connection()
        db = PaperDatabase.from_connection(con)
        neighbor_pairs = db.find_neighbors(paper_id, k=k, mutual=mutual)
        ids_to_fetch = [paper_id] + [pid for pid, _ in neighbor_pairs]
        rows = db.get_papers_by_ids(ids_to_fetch)

    by_id = {row[2]: row for row in rows}
    if paper_id not in by_id:
        return {"error": f"paper {paper_id!r} not found"}, 404

    seed_paper, _ = Paper.from_database_row(by_id[paper_id])
    neighbors_out: list[dict[str, Any]] = []
    for pid, sim in neighbor_pairs:
        if pid not in by_id:
            continue  # very rare: paper deleted between the two queries
        nb_paper, _ = Paper.from_database_row(by_id[pid])
        neighbors_out.append(_serialize_paper(nb_paper, similarity=sim))

    return {
        "seed": _serialize_paper(seed_paper),
        "neighbors": neighbors_out,
    }, 200


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile on an already-sorted list.

    ``pct`` is in [0, 100]. Mirrors numpy's default ("linear") method so
    results match what a casual reader would expect, without pulling numpy
    into the request path.
    """
    n = len(sorted_values)
    assert n > 0, "cannot compute percentile of empty list"
    if n == 1:
        return float(sorted_values[0])
    rank = (pct / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _compute_similarity_distribution(sample_size: int) -> dict[str, float]:
    """Sample pairwise similarities and reduce them to a percentile dict."""
    with _neighbors_conn_lock:
        con = _get_neighbors_connection()
        db = PaperDatabase.from_connection(con)
        sims = db.sample_pairwise_similarities(sample_size)
    if not sims:
        return {
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "p99_5": 0.0,
            "p99_9": 0.0,
        }
    sims.sort()
    return {
        "p50": _percentile(sims, 50),
        "p90": _percentile(sims, 90),
        "p95": _percentile(sims, 95),
        "p99": _percentile(sims, 99),
        "p99_5": _percentile(sims, 99.5),
        "p99_9": _percentile(sims, 99.9),
    }


@app.get("/api/embeddings/similarity_distribution")
def embeddings_similarity_distribution() -> tuple[dict[str, Any], int]:
    """Return cosine-similarity percentiles for random pairs of embedded papers.

    The frontend uses these to anchor the threshold slider in corpus
    percentiles ("0.71 is the 99th percentile of pairwise similarity in your
    corpus") rather than asking the user to pick a raw cosine number.

    The sample is computed lazily on first request and cached in-memory for
    the lifetime of the process. Pass ``?refresh=1`` to force recomputation.
    """
    global _similarity_distribution_cache

    refresh_raw = request.args.get("refresh", "0").strip().lower()
    refresh = refresh_raw in {"1", "true", "yes"}

    with _similarity_distribution_lock:
        if refresh or _similarity_distribution_cache is None:
            _similarity_distribution_cache = _compute_similarity_distribution(
                _similarity_distribution_sample_size
            )
        payload = dict(_similarity_distribution_cache)

    return payload, 200


def _next_conference_dates(
    latest: dict[str, date],
) -> dict[str, dict[str, Any]]:
    """Project the next conference date for each source.

    Keeps adding one year to the last known date until the projected date
    is in the future (or today).  Returns a dict keyed by source name with
    ``date`` (ISO string) and ``passed`` (bool).
    """
    today = date.today()
    result: dict[str, dict[str, Any]] = {}
    for source, last_date in latest.items():
        next_date = last_date.replace(year=last_date.year + 1)
        while next_date < today:
            next_date = next_date.replace(year=next_date.year + 1)
        result[source] = {
            "date": next_date.isoformat(),
            "passed": False,
        }
    return result


@app.get("/api/inventory")
def inventory() -> tuple[dict, int]:
    """Return a summary of conferences/years and paper counts in the database."""
    with PaperDatabase() as db:
        conferences = db.summarise_current_conferences()
        counts = db.count_papers_by_source()
        latest = db.latest_conference_dates()

    return {
        "conferences": conferences,
        "counts": counts,
        "next_dates": _next_conference_dates(latest),
    }, 200


@app.post("/api/sync")
def sync() -> tuple[dict[str, str], int]:
    """
    Synchronize ArXiv repository by fetching new papers and embedding them.
    This endpoint initializes an ArXivRepository and calls its sync method.
    """
    try:
        # Initialize ArXivRepository with same model configurations as used elsewhere
        with ArXivRepository(
            embedding_model_name="models/gemini-embedding-001",
            research_llm_model_name="google/gemini-2.5-flash",
        ) as arxiv_repo:
            arxiv_repo.sync()

        return {
            "status": "success",
            "message": "ArXiv repository sync completed successfully",
        }, 200

    except Exception as e:
        # Log the error for debugging but return a safe error message
        app.logger.error(f"Error during ArXiv sync: {str(e)}")
        return {"status": "error", "message": f"Sync failed: {str(e)}"}, 500


@app.post("/api/digest")
def digest() -> tuple[dict[str, str], int]:
    """
    Send email digest to research listener group without updating the repository.
    This endpoint initializes an ArXivRepository and calls email_daily_digest method.
    """
    try:
        # Initialize ArXivRepository with same model configurations as used elsewhere
        with ArXivRepository(
            embedding_model_name="models/gemini-embedding-001",
            research_llm_model_name="google/gemini-2.5-flash",
        ) as arxiv_repo:
            # Send email digest without syncing (same as --digest --no-sync)
            arxiv_repo.email_weekly_digest(research_listener_group)

        return {"status": "success", "message": "Email digest sent successfully"}, 200

    except Exception as e:
        # Log the error for debugging but return a safe error message
        app.logger.error(f"Error during digest email: {str(e)}")
        return {"status": "error", "message": f"Digest email failed: {str(e)}"}, 500


if __name__ == "__main__":
    # Bind to all interfaces for local dev; port can be overridden via FLASK_PORT
    port = int(os.getenv("FLASK_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
