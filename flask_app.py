from datetime import timedelta
import os
from typing import Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

from PaperRepository import PaperRepository

# Load environment variables early so repo/db can connect
load_dotenv()

app = Flask(__name__)
# Allow local Next.js dev server by default; can be customized with CORS_ORIGINS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
CORS(app, resources={r"/api/*": {"origins": cors_origins}})


@app.get("/api/health")
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


def _build_filters(repo: PaperRepository, sources_flags: Dict[str, bool]) -> List[str]:
    filters: List[str] = []

    # Map flags to source lists
    if sources_flags.get("arxiv", False):
        filters.append(repo.build_filter_string(["arxiv"]))

    if sources_flags.get("ai", False):
        filters.append(repo.build_filter_string(["ICML", "NeurIPS", "ICLR"]))

    if sources_flags.get("systems", False):
        filters.append(repo.build_filter_string(["OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys"]))

    # If nothing selected, default to everything
    if len(filters) == 0:
        filters.append(repo.build_filter_string([
            "arxiv",
            "ICML", "NeurIPS", "ICLR",
            "OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys",
        ]))

    return filters


@app.post("/api/search")
@app.get("/api/search")
def search() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    # Support query params for GET as well
    if request.method == "GET" and not body:
        body = {
            "text": request.args.get("text", ""),
            "time_window_days": request.args.get("time_window_days"),
            "sources": {
                "arxiv": request.args.get("arxiv", "false").lower() == "true",
                "ai": request.args.get("ai", "false").lower() == "true",
                "systems": request.args.get("systems", "false").lower() == "true",
            }
        }

    query_text: str = body.get("text", "").strip()
    if not query_text:
        return {"error": "text is required"}, 400

    time_window_days = body.get("time_window_days")
    try:
        time_window_days_int = int(time_window_days) if time_window_days is not None else 365 * 5
    except Exception:
        return {"error": "time_window_days must be an integer"}, 400

    sources_flags: Dict[str, bool] = body.get("sources", {}) or {}

    # Use repository in a context so connections are properly managed
    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        filters = _build_filters(repo, sources_flags)
        papers = repo.get_newest_related_papers(
            query_text,
            timedelta(days=time_window_days_int),
            filters,
        )

    results = []
    for p in papers:
        results.append({
            "paper_id": p.paper_id,
            "title": p.title,
            "abstract": p.abstract,
            "source": p.source,
            "link": p.link,
            # paper_date is a datetime.date or datetime; convert to ISO string
            "paper_date": p.paper_date.isoformat() if hasattr(p.paper_date, "isoformat") else str(p.paper_date),
        })

    return {"results": results}, 200


if __name__ == "__main__":
    # Bind to all interfaces for local dev; port can be overridden via FLASK_PORT
    port = int(os.getenv("FLASK_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
