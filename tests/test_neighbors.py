"""Smoke test + latency budget check for ``/api/papers/<id>/neighbors``.

Talks to the live dev database (postgres on localhost). Skips if the DB or
the Flask app cannot be reached.

Latency budgets, asserted over 50 trials each:
    mutual=false  p95 <= 30ms
    mutual=true   p95 <= 200ms
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

import pytest

# Ensure src/ is on the path and the local DB URL is used.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://oversight:q%5EAX%40Z66QZ2SMPkJ@localhost:5432/oversight",
)

import psycopg  # noqa: E402

from oversight.flask_app import app  # noqa: E402
from oversight.PaperDatabase import PaperDatabase  # noqa: E402


def _db_available() -> bool:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as _:
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="dev postgres not reachable on localhost:5432",
)


TRIALS = 50
WARMUP = 5


def _percentile(values: list[float], pct: float) -> float:
    s = sorted(values)
    idx = int(round((pct / 100) * (len(s) - 1)))
    return s[idx]


@pytest.fixture(scope="module")
def client():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(scope="module")
def seed_paper_id() -> str:
    random.seed(0)
    with PaperDatabase() as db:
        with db._get_con().cursor() as cur:
            row = cur.execute(
                "SELECT paper_id FROM embedding "
                "WHERE embedding_gemini_embedding_001 IS NOT NULL "
                "ORDER BY random() LIMIT 1"
            ).fetchone()
    assert row is not None, "no embedded papers in DB"
    return row[0]


def _assert_response_shape(payload: dict, *, expect_neighbors: bool) -> None:
    assert "seed" in payload, payload
    seed = payload["seed"]
    assert isinstance(seed, dict)
    for field in ("paper_id", "title", "authors"):
        assert field in seed, f"seed missing {field!r}"

    assert "neighbors" in payload
    neighbors = payload["neighbors"]
    assert isinstance(neighbors, list)
    if expect_neighbors:
        assert len(neighbors) > 0, "expected at least one neighbor"
    for n in neighbors:
        for field in ("paper_id", "title", "authors", "similarity"):
            assert field in n, f"neighbor missing {field!r}: {n}"
        assert isinstance(n["similarity"], (int, float))
        # Cosine similarity is in [-1, 1]; in practice on this corpus > 0.
        assert -1.0 <= n["similarity"] <= 1.0
        assert n["paper_id"] != seed["paper_id"], "seed leaked into neighbors"


def test_topk_response_shape(client, seed_paper_id):
    resp = client.get(f"/api/papers/{seed_paper_id}/neighbors?k=20&mutual=false")
    assert resp.status_code == 200, resp.data
    _assert_response_shape(resp.get_json(), expect_neighbors=True)


def test_mutual_response_shape(client, seed_paper_id):
    resp = client.get(f"/api/papers/{seed_paper_id}/neighbors?k=20&mutual=true")
    assert resp.status_code == 200, resp.data
    # Mutual mode can return zero neighbors for sparse-region seeds.
    _assert_response_shape(resp.get_json(), expect_neighbors=False)


def test_invalid_k_rejected(client, seed_paper_id):
    resp = client.get(f"/api/papers/{seed_paper_id}/neighbors?k=0")
    assert resp.status_code == 400
    resp = client.get(f"/api/papers/{seed_paper_id}/neighbors?k=51")
    assert resp.status_code == 400
    resp = client.get(f"/api/papers/{seed_paper_id}/neighbors?k=abc")
    assert resp.status_code == 400


def test_unknown_paper_returns_404(client):
    resp = client.get("/api/papers/__definitely_not_a_real_paper__/neighbors")
    assert resp.status_code == 404


def _bench_endpoint(client, paper_id: str, mutual: bool, trials: int) -> list[float]:
    times_ms: list[float] = []
    url = f"/api/papers/{paper_id}/neighbors?k=20&mutual={'true' if mutual else 'false'}"
    for _ in range(trials):
        t0 = time.perf_counter()
        resp = client.get(url)
        dt = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200
        times_ms.append(dt)
    return times_ms


def test_topk_latency_budget(client, seed_paper_id):
    """p95 <= 30ms over 50 trials for the default top-k mode."""
    # Warm up the connection / pgvector index.
    _bench_endpoint(client, seed_paper_id, mutual=False, trials=WARMUP)
    times = _bench_endpoint(client, seed_paper_id, mutual=False, trials=TRIALS)
    p50 = _percentile(times, 50)
    p95 = _percentile(times, 95)
    print(
        f"\n[topk]    p50={p50:.1f}ms p95={p95:.1f}ms "
        f"max={max(times):.1f}ms over {TRIALS} trials"
    )
    assert p95 <= 30.0, f"top-k p95 {p95:.1f}ms exceeded 30ms budget"


def test_mutual_latency_budget(client, seed_paper_id):
    """p95 <= 200ms over 50 trials for mutual-kNN mode."""
    _bench_endpoint(client, seed_paper_id, mutual=True, trials=WARMUP)
    times = _bench_endpoint(client, seed_paper_id, mutual=True, trials=TRIALS)
    p50 = _percentile(times, 50)
    p95 = _percentile(times, 95)
    print(
        f"\n[mutual]  p50={p50:.1f}ms p95={p95:.1f}ms "
        f"max={max(times):.1f}ms over {TRIALS} trials"
    )
    assert p95 <= 200.0, f"mutual-kNN p95 {p95:.1f}ms exceeded 200ms budget"
