"""c-TF-IDF labels for atlas clusters.

Given a precomputed HDBSCAN cluster tree (``atlas_cluster``,
``atlas_cluster_member``) and a global term-frequency sidecar
(``atlas_cluster_term_idf`` + ``atlas_cluster_term_stats``), generate
a short keyword label for a single cluster.

The c-TF-IDF formulation:

    tf_t,c   = count of term t in cluster c's document
              (cluster doc = concatenation of titles + first-200-char
               abstract prefixes for the cluster's papers)
    idf_t    = log(N / nt) where N = total #clusters and nt = #clusters
              containing t at least once
    score_t,c = tf_t,c * idf_t

We then drop:
- terms appearing in >95% of clusters (uninformative)
- pure-numeric or 1-2 char tokens (the tokenizer in
  ``build_atlas_clusters.py`` already throws those out, but we also
  defend here in case the sidecar was built with different rules)
- duplicate lemma prefixes within a single label (e.g. "type" vs
  "types") — we keep only the first occurrence of any prefix that
  shares the first 5 characters

Top 3 keywords joined with " · " become the label.

Persistence: ``compute_and_cache_cluster_labels`` does a single
SELECT-then-INSERT per call; the rows persist forever (clusters are
immutable for a given projection).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


# Mirror the tokenizer used by build_atlas_clusters.py — terms missing
# from the global IDF table by virtue of a different tokenizer pass
# would have IDF=infinity and dominate every label. Keep both in sync.
_STOPWORDS: frozenset[str] = frozenset(
    """
a an and or of for to from in on at by with into onto over under between
the this that these those is are was were be been being am do does did
have has had having will would should could may might must can shall
not no nor so as if then than but also too very more most much less few
many some any all every other another such same own its their them they
we us our you your he she it him her his hers
i me my mine myself yourself himself herself itself ourselves themselves
about above after again against among around because before below beside
during except inside outside since through throughout toward towards until
upon via within without
paper papers work works study studies result results show shows shown
showing approach approaches method methods propose proposes proposed
proposing present presents presented presenting use uses used using
new novel framework system systems based perform performs performed
performance experiment experiments experimental evaluation evaluations
also however therefore thus furthermore moreover additionally
""".split()
)

_TOKEN_RE = re.compile(r"[a-z][a-z\-]{1,}")


def _tokenize(text: str) -> list[str]:
    """Lower-cased single-token list, dropping stopwords and short bits.

    Mirrored from build_atlas_clusters.py so the term tokens we look up
    in atlas_cluster_term_idf match those that were counted at build
    time.
    """
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        tok = tok.strip("-")
        if len(tok) < 3:
            continue
        if tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _ngrams(tokens: list[str]) -> list[str]:
    """Unigrams + bigrams as flat strings, suitable for c-TF-IDF."""
    out: list[str] = list(tokens)
    for a, b in zip(tokens, tokens[1:]):
        out.append(f"{a} {b}")
    return out


# In-process cache for the global IDF sidecar. Keyed by projection.
# Loaded once per process per projection on first label miss; never
# invalidated — the sidecar is immutable once the cluster build runs.
_idf_cache: dict[str, tuple[dict[str, int], int]] = {}


def _load_global_idf(
    con: psycopg.Connection[Any], projection: str
) -> tuple[dict[str, int], int]:
    """Return (term_doc_count, total_docs) for this projection, cached."""
    cached = _idf_cache.get(projection)
    if cached is not None:
        return cached
    with con.cursor() as cur:
        cur.execute(
            "SELECT doc_count FROM atlas_cluster_term_stats WHERE projection = %s",
            [projection],
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(
                f"No atlas_cluster_term_stats row for projection={projection!r}; "
                "run scripts/build_atlas_clusters.py first."
            )
        total_docs = int(row[0])

        cur.execute(
            "SELECT term, cluster_count FROM atlas_cluster_term_idf "
            "WHERE projection = %s",
            [projection],
        )
        term_doc_count = {term: int(cnt) for term, cnt in cur.fetchall()}

    _idf_cache[projection] = (term_doc_count, total_docs)
    return term_doc_count, total_docs


def _dedupe_by_stem(keywords: list[str], n: int) -> list[str]:
    """Pick the first ``n`` keywords with no shared 5-char prefix.

    Cheap stand-in for proper lemmatization. Stops "type", "types",
    "typed" from all showing up in a single 3-keyword label.
    """
    out: list[str] = []
    seen_stems: set[str] = set()
    for kw in keywords:
        # For bigrams, dedupe on the first word's stem.
        first = kw.split(" ", 1)[0]
        stem = first[:5]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        out.append(kw)
        if len(out) >= n:
            break
    return out


def _format_label(keywords: list[str]) -> str:
    """Join with ' · ' and trim trailing punctuation; safe for HTML."""
    return " · ".join(keywords).strip()


def compute_cluster_label(
    con: psycopg.Connection[Any],
    projection: str,
    cluster_id: int,
    *,
    top_n: int = 3,
    drop_above_df_ratio: float = 0.95,
) -> tuple[str, list[str]]:
    """Compute the c-TF-IDF label for one cluster.

    Returns ``(label_string, keywords_list)``. Does not insert into
    ``atlas_cluster_label`` — that's the caller's responsibility
    (so the API endpoint can batch inserts).
    """
    term_doc_count, total_docs = _load_global_idf(con, projection)
    if total_docs == 0:
        return "", []

    df_cutoff = int(total_docs * drop_above_df_ratio)

    with con.cursor() as cur:
        cur.execute(
            """
            SELECT p.title, p.abstract
            FROM atlas_cluster_member m
            JOIN paper p ON p.paper_id = m.paper_id
            WHERE m.projection = %s AND m.cluster_id = %s
            """,
            [projection, cluster_id],
        )
        rows = cur.fetchall()

    if not rows:
        return "", []

    # Tally tf for this cluster.
    tf: Counter[str] = Counter()
    for title, abstract in rows:
        toks = _tokenize(f"{title or ''}\n{(abstract or '')[:200]}")
        for ng in _ngrams(toks):
            tf[ng] += 1

    # Compute c-TF-IDF scores.
    scored: list[tuple[str, float]] = []
    for term, tf_val in tf.items():
        df = term_doc_count.get(term)
        if not df:
            # Term wasn't in the global vocab — skip rather than divide
            # by zero. (Shouldn't happen if the sidecar covers all
            # current members; can happen for legacy clusters whose
            # papers were re-ingested with different content.)
            continue
        if df > df_cutoff:
            # Appears in >95% of clusters — too generic to inform.
            continue
        idf = math.log(total_docs / df) + 1.0  # +1 keeps IDF positive
        scored.append((term, tf_val * idf))

    scored.sort(key=lambda kv: kv[1], reverse=True)
    keyword_pool = [t for t, _ in scored]

    # Slight preference for bigrams when their score is close to a
    # unigram's: bigrams ("type theory") are more readable as labels
    # than unigrams ("type"). We re-rank by giving bigrams a 1.15x
    # multiplier and re-sorting the top 30.
    if scored:
        rerank: list[tuple[str, float]] = []
        for term, score in scored[:30]:
            mult = 1.15 if " " in term else 1.0
            rerank.append((term, score * mult))
        rerank.sort(key=lambda kv: kv[1], reverse=True)
        keyword_pool = [t for t, _ in rerank] + keyword_pool[30:]

    top_keywords = _dedupe_by_stem(keyword_pool, top_n)
    return _format_label(top_keywords), top_keywords


def cache_label(
    con: psycopg.Connection[Any],
    projection: str,
    cluster_id: int,
    label: str,
    keywords: list[str],
    method: str = "c_tfidf_v1",
) -> None:
    """Insert a row into ``atlas_cluster_label`` (idempotent via ON CONFLICT)."""
    with con.cursor() as cur:
        cur.execute(
            """
            INSERT INTO atlas_cluster_label (projection, cluster_id, label, keywords, method)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (projection, cluster_id) DO UPDATE SET
                label = EXCLUDED.label,
                keywords = EXCLUDED.keywords,
                method = EXCLUDED.method,
                generated_at = CURRENT_TIMESTAMP
            """,
            [projection, cluster_id, label, Jsonb(keywords), method],
        )
