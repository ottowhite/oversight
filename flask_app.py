from datetime import timedelta
import os
from typing import Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

from PaperRepository import PaperRepository
from ArXivRepository import ArXivRepository
from ResearchListener import research_listener_group

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
    
    # Collect individual sources
    selected_sources = []
    
    # Handle arXiv
    if sources_flags.get("arxiv", False):
        selected_sources.append("arxiv")
    
    # Handle individual AI conferences
    ai_conferences = ["ICML", "NeurIPS", "ICLR"]
    for conf in ai_conferences:
        if sources_flags.get(conf, False):
            selected_sources.append(conf)
    
    # Handle individual Systems conferences  
    systems_conferences = ["OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys", "VLDB"]
    for conf in systems_conferences:
        if sources_flags.get(conf, False):
            selected_sources.append(conf)
    
    # Build filter from selected sources
    if selected_sources:
        filters.append(repo.build_filter_string(selected_sources))
    else:
        # If nothing selected, default to everything
        filters.append(repo.build_filter_string([
            "arxiv",
            "ICML", "NeurIPS", "ICLR", 
            "OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys", "VLDB"
        ]))

    return filters


@app.post("/api/search")
@app.get("/api/search")
def search() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    # Support query params for GET as well
    if request.method == "GET" and not body:
        # Create sources dict from individual conference params
        sources = {
            "arxiv": request.args.get("arxiv", "false").lower() == "true",
        }
        
        # Add individual AI conferences
        ai_conferences = ["ICML", "NeurIPS", "ICLR"]
        for conf in ai_conferences:
            sources[conf] = request.args.get(conf, "false").lower() == "true"
            
        # Add individual Systems conferences
        systems_conferences = ["OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys", "VLDB"]  
        for conf in systems_conferences:
            sources[conf] = request.args.get(conf, "false").lower() == "true"
        
        body = {
            "text": request.args.get("text", ""),
            "time_window_days": request.args.get("time_window_days"),
            "sources": sources
        }

    query_text: str = body.get("text", "").strip()
    if not query_text:
        return {"error": "text is required"}, 400

    time_window_days = body.get("time_window_days")
    try:
        time_window_days_int = int(time_window_days) if time_window_days is not None else 365 * 5
    except Exception:
        return {"error": "time_window_days must be an integer"}, 400

    limit = body.get("limit")
    try:
        limit_int = int(limit) if limit is not None else 10
        limit_int = max(1, min(100, limit_int))
    except Exception:
        return {"error": "limit must be an integer between 1 and 100"}, 400

    sources_flags: Dict[str, bool] = body.get("sources", {}) or {}

    # Use repository in a context so connections are properly managed
    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        filters = _build_filters(repo, sources_flags)
        papers = repo.get_newest_related_papers(
            query_text,
            timedelta(days=time_window_days_int),
            filters,
            limit=limit_int,
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


@app.post("/api/sync")
def sync() -> tuple[dict, int]:
    """
    Synchronize ArXiv repository by fetching new papers and embedding them.
    This endpoint initializes an ArXivRepository and calls its sync method.
    """
    try:
        # Initialize ArXivRepository with same model configurations as used elsewhere
        with ArXivRepository(
            embedding_model_name="models/gemini-embedding-001",
            research_llm_model_name="google/gemini-2.5-flash"
        ) as arxiv_repo:
            arxiv_repo.sync()
        
        return {"status": "success", "message": "ArXiv repository sync completed successfully"}, 200
    
    except Exception as e:
        # Log the error for debugging but return a safe error message
        app.logger.error(f"Error during ArXiv sync: {str(e)}")
        return {"status": "error", "message": f"Sync failed: {str(e)}"}, 500

@app.post("/api/digest")
def digest() -> tuple[dict, int]:
    """
    Send email digest to research listener group without updating the repository.
    This endpoint initializes an ArXivRepository and calls email_daily_digest method.
    """
    try:
        # Initialize ArXivRepository with same model configurations as used elsewhere
        with ArXivRepository(
            embedding_model_name="models/gemini-embedding-001",
            research_llm_model_name="google/gemini-2.5-flash"
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
