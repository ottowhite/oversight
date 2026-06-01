# Plan: ingest PL conference proceedings

## Motivation

The arxiv-CS harvester misses any paper that was never deposited on arxiv.
`Pure Subtype Systems` (Hutchins, POPL 2010) is the canonical example: the
paper is foundational PL work but exists only in the ACM Digital Library and
the author's PhD thesis. arxiv-only ingest will never see it.

A measurable chunk of the PL community publishes only in proceedings, so
filling that gap requires a second ingestion path that scrapes
proceedings directly. arxiv preprints already cover ~9.7k cs.PL papers in
the database; the goal here is to add the ~10–15k papers that exist only
behind ACM/Springer/LIPIcs DOIs.

## Conferences in scope

### Tier 1 — SIGPLAN flagship (PACMPL since 2017)

| Venue | Full name | Years | Volume |
|---|---|---|---|
| POPL | Principles of Programming Languages | 1973– | ~3,000 papers |
| PLDI | Programming Language Design & Implementation | 1979– | ~2,800 |
| ICFP | International Conference on Functional Programming | 1996– | ~1,200 |
| OOPSLA | Object-Oriented Programming, Systems, Languages, Apps (SPLASH) | 1986– | ~2,500 |

### Tier 2 — also clearly PL

| Venue | Full name | Years | Volume |
|---|---|---|---|
| ESOP | European Symposium on Programming (ETAPS) | 1986– | ~1,200 |
| ECOOP | European Conference on OO Programming (LIPIcs ≥2018) | 1987– | ~1,000 |
| CC | Compiler Construction (ACM, co-located with CGO) | 1986– | ~900 |
| Haskell Symposium | (co-located with ICFP) | 2007– | ~250 |

## Data sources

Both free, no auth, no realistic rate limits:

1. **DBLP** — canonical, exhaustive paper list per venue/year.
   Per-volume JSON endpoint: `https://dblp.org/db/conf/popl/popl2024.json`.
   Provides title, authors, DOIs, year. **No abstracts.**

2. **OpenAlex** — abstracts, affiliations, references, citations.
   DOI lookup: `https://api.openalex.org/works/https://doi.org/<DOI>`.
   Returns abstract as inverted index (reconstruct in client).
   ~100k req/day per identified email — well above what we need.

### Fallbacks for missing abstracts

OpenAlex coverage of these venues is essentially 100%, but pre-2017 ACM
papers occasionally have empty abstracts in Crossref. In order:

1. **Semantic Scholar API** — `https://api.semanticscholar.org/graph/v1/paper/DOI:<DOI>?fields=abstract,authors,year`. Filled in for ~all PL papers, including pre-2017.
2. **ACM Digital Library scrape** — landing page metadata is open even when full text is paywalled. Last resort; brittle.
3. **Skip** — log and move on. A title-only record is worse than no record because it pollutes search results without semantic signal.

## JSON output format

Reuse the existing `scraped` shape consumed by `Paper.from_scraped_json`
(`src/oversight/Paper.py:111`). Minimal required fields:

```json
{
  "paper_id": "10.1145/1706299.1706334",
  "title": "Pure Subtype Systems",
  "abstract": "We present a new approach to type theory called pure subtype systems...",
  "date": "2010-01-17",
  "link": "https://dl.acm.org/doi/10.1145/1706299.1706334",
  "conference_name": "POPL",
  "authors": [
    { "first_name": "DeLesley", "last_name": "Hutchins", "institution": "MZA Associates" }
  ]
}
```

`paper_id` should be the DOI when available — it's globally unique and
stable. Use `<venue>-<year>-<slug>` only when no DOI exists.

## New components

### 1. `PLConferenceHarvester.py`

Modeled on `OpenReviewHarvester.py`. Responsibilities:

- Take `(venue, year)` pairs.
- Fetch DBLP TOC for that volume.
- For each entry: fetch OpenAlex by DOI, fall back to Semantic Scholar, fall back to ACM scrape, fall back to skip-with-log.
- Emit one JSON file per (venue, year) at `data/pl_conferences/<venue>/<year>.json`.

### 2. Sync integration

Add a `make oversight/sync/pl` target that runs the harvester (with
`--skip-existing-doi` for cheap incremental behaviour — the DBLP TOC
is still walked but OpenAlex / Semantic Scholar lookups are short-
circuited for DOIs already in the DB) and then consumes the resulting
JSON into the database. Make `make oversight/sync` depend on both
`oversight/sync/arxiv` and `oversight/sync/pl`, so the daily cron
picks up both.

```make
oversight/sync: oversight/sync/arxiv oversight/sync/pl

oversight/sync/arxiv:
	uv run python -m oversight.ArXivRepository --sync

oversight/sync/pl:
	uv run python -m oversight.PLConferenceHarvester --skip-existing-doi
	uv run oversight consume data/pl_conferences/ --format scraped
```

No new abstractions. PL ingestion runs alongside arxiv via Make's
dependency mechanism. Earlier versions of this plan proposed a
`SourcePoller` protocol with one wrapper class per source; that was
landed and then reverted as over-engineered for the actual achieved
scope (only arxiv + PL would have ever used it). ML conferences and
systems conferences continue to use their existing ad-hoc workflows
until they have a real reason to migrate.

### 3. Embedding pass

No change required. `PaperDatabase.get_unembedded_conference_papers()`
already picks up any paper with `source != 'arxiv'` and a NULL embedding,
so PL papers will be embedded automatically on the next sync.

## Implementation phases

### Phase 1 — vertical slice (1–2 hrs)

- [ ] `PLConferenceHarvester` hardcoded to POPL 2024 only.
- [ ] DBLP fetch → OpenAlex fetch → emit JSON.
- [ ] Manual `oversight consume data/pl_conferences/popl/2024.json --format scraped`.
- [ ] Verify search surfaces a known POPL 2024 paper.
- [ ] Verify the embedding pass runs over the new rows.

Acceptance: `oversight search "separation logic" --sources POPL` returns
sensible results.

### Phase 2 — back-catalogue (one-shot)

- [ ] Expand to all Tier 1 + Tier 2 venues, all years DBLP has.
- [ ] Run the harvester across all venues; let it write JSON files
      under `data/pl_conferences/<venue>/<year>.json`.
- [ ] `oversight consume data/pl_conferences/ --format scraped` to
      load them and trigger embedding (~10–15k new papers; cost low).
- [ ] Spot-check Hutchins POPL 2010 lands in the DB.

### Phase 3 — sync integration

- [ ] Add `oversight/sync/pl` Make target running the harvester +
      consume, with `--skip-existing-doi` for incremental behaviour.
- [ ] Wire `oversight/sync` to depend on both arxiv and PL sync targets.
- [ ] Daily cron picks up new PL volumes when DBLP indexes them.

## Scope estimate

| Tier | Conferences | Total papers | Embedding cost (approx) |
|---|---|---:|---|
| 1 | POPL, PLDI, ICFP, OOPSLA | ~9,500 | low |
| 2 | ESOP, ECOOP, CC, Haskell | ~3,400 | low |

Storage impact: at ~16 KB/paper average (current ratio), full Tier 1+2
adds ~210 MB. Negligible against current 15 GB.

## Risks and edge cases

- **Pre-2017 ACM papers without abstracts in Crossref** — handled by
  Semantic Scholar fallback.
- **DBLP TOC URL pattern changes** — fragile; pin to current scheme and
  add a smoke test that fetches POPL 2024 on every CI run.
- **DOI collisions across venues** — shouldn't happen for proceedings,
  but enforce uniqueness on `paper_id` (already a unique constraint).
- **Workshops co-located with main conferences** (PEPM with POPL,
  TyDe with ICFP) — DBLP lists these as separate volumes. Decision: ignore
  for now, revisit if users notice the gap.
- **Joint papers in arxiv + proceedings** — same paper, two `paper_id`s
  (arxiv ID and DOI). Defer dedup until after Phase 2 lands. Once every
  venue is in the database we can query actual title/author overlap and
  quantify the duplication, then choose a dedup strategy with real
  numbers rather than guesses. Don't pre-optimize before we have data.
