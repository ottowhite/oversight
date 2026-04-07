from __future__ import annotations

from typing import Any

from tqdm import tqdm
from Paper import Paper
from datetime import date, datetime, timedelta
import psycopg
from psycopg import sql
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
import os
from psycopg.types.json import Jsonb
from utils import get_logger

logger = get_logger()


class PaperDatabase:
    def __init__(self) -> None:
        load_dotenv()
        self.ai_categories = ["cs:cs:AI", "cs:cs:CL", "cs:cs:LG", "cs:cs:MA"]
        self.con: psycopg.Connection[tuple[Any, ...]] | None = None
        self.date_format = "%Y-%m-%d"

    def __enter__(self) -> PaperDatabase:
        database_url = os.getenv("DATABASE_URL")
        assert database_url is not None, "Database URL is not set"
        self.con = psycopg.connect(database_url)
        register_vector(self.con)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        # NOTE: The commit only happens at the very end, and if there was an error, we will not commit.
        if self.con is not None:
            if exc_type is None:
                self.con.commit()
            else:
                print(f"Error committing transaction:\n{exc_value}")

            self.con.close()
            self.con = None

    def _get_con(self) -> psycopg.Connection[tuple[Any, ...]]:
        assert self.con is not None, (
            "Database connection not established. Use 'with' statement."
        )
        return self.con

    def insert_paper(self, paper: Paper) -> tuple[int, int, int]:
        with self._get_con().cursor() as cur:
            to_insert = [
                paper.paper_id,
                Jsonb(paper.document),
                paper.abstract,
                paper.title,
                paper.source,
                paper.paper_date.strftime(self.date_format),
                paper.link,
            ]

            if any(v is None for v in to_insert):
                breakpoint()

            # First, try to update an existing paper if the incoming record is newer
            updated_rows = cur.execute(
                """
                UPDATE paper
                SET document = %s::jsonb,
                    abstract = %s,
                    title = %s,
                    source = %s,
                    update_date = %s,
                    link = %s
                WHERE paper_id = %s::VARCHAR
                  AND update_date < %s::DATE
                """,
                [
                    Jsonb(paper.document),
                    paper.abstract,
                    paper.title,
                    paper.source,
                    paper.paper_date.strftime(self.date_format),
                    paper.link,
                    paper.paper_id,
                    paper.paper_date.strftime(self.date_format),
                ],
            ).rowcount

            new_rows = 0
            skipped_rows = 0
            if updated_rows == 0:
                # If no update happened, try to insert (noop if already exists with newer/same date)
                new_rows = cur.execute(
                    """
                    INSERT INTO paper (paper_id, document, abstract, title, source, update_date, link)
                    VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s)
                    ON CONFLICT (paper_id) DO NOTHING;
                    """,
                    to_insert,
                ).rowcount
            else:
                # Paper content changed; reset embedding for this paper so it gets re-embedded
                cur.execute(
                    """
                    UPDATE embedding
                    SET embedding_gemini_embedding_001 = NULL
                    WHERE paper_id = %s::VARCHAR
                    """,
                    [paper.paper_id],
                )

            skipped_rows = 1 - (updated_rows + new_rows)

            assert new_rows + updated_rows + skipped_rows == 1, (
                f"Updated {updated_rows} rows, inserted {new_rows} rows, and skipped {skipped_rows} rows for paper {paper.paper_id}"
            )

            return updated_rows, new_rows, skipped_rows

    def is_updated(self, paper: Paper) -> bool:
        with self._get_con().cursor() as cur:
            return (
                cur.execute(
                    """
                SELECT 1 FROM paper
                WHERE paper_id = %s::VARCHAR AND update_date < %s::DATE
            """,
                    [paper.paper_id, paper.paper_date.strftime(self.date_format)],
                ).fetchone()
                is not None
            )

    def is_new(self, paper: Paper) -> bool:
        with self._get_con().cursor() as cur:
            return (
                cur.execute(
                    """
                SELECT 1 FROM paper
                WHERE paper_id = %s::VARCHAR
            """,
                    [paper.paper_id],
                ).fetchone()
                is None
            )

    def get_newest_date(self) -> datetime:
        with self._get_con().cursor() as cur:
            row = cur.execute("SELECT MAX(update_date) FROM paper").fetchone()
            assert row is not None, "No papers in database"
            return row[0]

    def try_update_categories(self, paper: Paper) -> bool:
        with self._get_con().cursor() as cur:
            stored_categories = cur.execute(
                """
                SELECT category FROM arxiv_paper_categories
                WHERE paper_id = %s::VARCHAR
            """,
                [paper.paper_id],
            ).fetchall()
            stored_categories_set = {c[0] for c in stored_categories}

            if stored_categories_set == paper.categories:
                return False

            # Delete the existing categories
            cur.execute(
                """
                DELETE FROM arxiv_paper_categories
                WHERE paper_id = %s::VARCHAR
            """,
                [paper.paper_id],
            )

            # Add the new categories
            assert paper.categories is not None
            bulk_insertions = []
            for category in paper.categories:
                bulk_insertions.append((paper.paper_id, category))
            cur.executemany(
                """
                INSERT INTO arxiv_paper_categories (paper_id, category)
                VALUES (%s, %s)
            """,
                bulk_insertions,
            )

        return True

    def get_unembedded_arxiv_ai_papers(self) -> list[tuple[Any, ...]]:
        query = sql.SQL("""
                SELECT DISTINCT ps.paper_id, ps.document
                FROM paper AS ps
                JOIN arxiv_paper_categories AS pc
                  ON ps.paper_id = pc.paper_id
                LEFT JOIN embedding AS se
                  ON se.paper_id = ps.paper_id
                WHERE se.embedding_gemini_embedding_001 IS NULL
                  AND pc.category IN ({categories})
            """).format(
            categories=sql.SQL(",").join(sql.Literal(c) for c in self.ai_categories)
        )
        with self._get_con().cursor() as cur:
            return cur.execute(query).fetchall()

    def get_unembedded_conference_papers(self) -> list[tuple[Any, ...]]:
        with self._get_con().cursor() as cur:
            return cur.execute("""
                SELECT DISTINCT ps.paper_id, ps.abstract
                FROM paper AS ps
                LEFT JOIN embedding AS emb
                  ON emb.paper_id = ps.paper_id
                WHERE emb.embedding_gemini_embedding_001 IS NULL
                  AND ps.source != 'arxiv'
            """).fetchall()

    def update_embedding(self, paper_id: str, embedding: list[float]) -> None:
        with self._get_con().cursor() as cur:
            cur.execute(
                """
                INSERT INTO embedding (paper_id, embedding_gemini_embedding_001)
                VALUES (%s::VARCHAR, %s::halfvec(3072))
                ON CONFLICT (paper_id) DO UPDATE
                SET embedding_gemini_embedding_001 = EXCLUDED.embedding_gemini_embedding_001
                """,
                [paper_id, embedding],
            )

    def count_rows_to_update_and_insert(self, papers: list[Paper]) -> tuple[int, int]:
        total_updates = 0
        total_new = 0
        for paper in tqdm(
            papers, desc="Checking for paper updates and new papers", total=len(papers)
        ):
            total_updates += self.is_updated(paper)
            total_new += self.is_new(paper)

        return total_updates, total_new

    def generate_weekly_digest(
        self, embedding: list[float], limit: int = 10
    ) -> list[tuple[Any, ...]]:
        last_day = datetime.now() - timedelta(days=7)
        with self._get_con().cursor() as cur:
            rows = cur.execute(
                """
                SELECT ps.*, emb.embedding_gemini_embedding_001 <=> %s::halfvec(3072) AS similarity
                FROM paper AS ps
                LEFT JOIN embedding AS emb
                  ON emb.paper_id = ps.paper_id
                WHERE ps.update_date > %s::DATE
                ORDER BY similarity ASC
                LIMIT %s
            """,
                [embedding, last_day, limit],
            ).fetchall()

        return rows

    def time_filtered_k_nearest(
        self, embedding: list[float], timedelta: timedelta | None, limit: int
    ) -> list[tuple[Any, ...]]:
        if timedelta is not None:
            oldest_time = (datetime.now() - timedelta).strftime("%Y-%m-%d")
            time_filter = sql.SQL("WHERE update_date > {oldest_time}").format(
                oldest_time=sql.Literal(oldest_time)
            )
        else:
            time_filter = sql.SQL("")

        query = sql.SQL("""
                SELECT ps.document, emb.embedding_gemini_embedding_001 <=> %s::halfvec(3072) AS similarity
                FROM paper AS ps
                LEFT JOIN embedding AS emb
                  ON emb.paper_id = ps.paper_id
                {time_filter}
                ORDER BY similarity ASC
                LIMIT %s::INTEGER
            """).format(time_filter=time_filter)
        with self._get_con().cursor() as cur:
            return cur.execute(query, [embedding, limit]).fetchall()

    def get_newest_conference_papers(
        self, embedding: list[float], timedelta: timedelta
    ) -> list[tuple[Any, ...]]:
        limit = 10
        if timedelta is None:
            timedelta = timedelta(days=365 * 50)

        oldest_time = (datetime.now() - timedelta).strftime("%Y-%m-%d")

        with self._get_con().cursor() as cur:
            return cur.execute(
                """
                SELECT ps.*, emb.embedding_gemini_embedding_001 <=> %s::halfvec(3072) AS similarity
                FROM paper AS ps
                JOIN embedding AS emb
                  ON emb.paper_id = ps.paper_id
                WHERE ps.update_date > %s::DATE
                  AND ps.source != 'arxiv'
                  AND emb.embedding_gemini_embedding_001 IS NOT NULL
                ORDER BY similarity ASC
                LIMIT %s::INTEGER
            """,
                [embedding, oldest_time, limit],
            ).fetchall()

    def get_newest_papers(
        self,
        embedding: list[float],
        timedelta: timedelta,
        filter_list: list[sql.Composable],
        limit: int = 10,
        ef_search: int = 40,
    ) -> list[tuple[Any, ...]]:
        if timedelta is None:
            timedelta = timedelta(days=365 * 50)

        oldest_time = (datetime.now() - timedelta).strftime("%Y-%m-%d")

        # Combine multiple filters with OR (union of sources), wrapped to preserve precedence
        if filter_list:
            or_group = sql.SQL(" OR ").join(
                sql.SQL("({})").format(flt) for flt in filter_list
            )
            filter_composed = sql.SQL("AND ({})").format(or_group)
        else:
            filter_composed = sql.SQL("")

        query = sql.SQL("""
                SELECT ps.*, emb.embedding_gemini_embedding_001 <=> %s::halfvec(3072) AS similarity
                FROM paper AS ps
                JOIN embedding AS emb
                  ON emb.paper_id = ps.paper_id
                WHERE ps.update_date > %s::DATE
                  AND emb.embedding_gemini_embedding_001 IS NOT NULL
                {filter_str}
                ORDER BY similarity ASC
                LIMIT %s::INTEGER
            """).format(filter_str=filter_composed)
        with self._get_con().cursor() as cur:
            cur.execute(
                sql.SQL("SET hnsw.ef_search = {}").format(sql.Literal(ef_search))
            )
            return cur.execute(query, [embedding, oldest_time, limit]).fetchall()

    def latest_conference_dates(self) -> dict[str, date]:
        """Return the most recent paper date for each non-arxiv source."""
        with self._get_con().cursor() as cur:
            rows = cur.execute(
                """
                SELECT source, MAX(update_date)::DATE
                FROM paper
                WHERE source != 'arxiv'
                GROUP BY source
                """
            ).fetchall()
        return {source: d for source, d in rows}

    def summarise_current_conferences(self) -> dict[str, dict[int, int]]:
        """Print a summary of the conference papers that are currently in the
        database. For every non-arxiv paper source (e.g. ICML, NeurIPS, …)
        print the list of years for which we have papers.
        Example output::
            ICML      : [2022, 2023, 2024]
            NeurIPS   : [2021, 2022, 2023]
        """
        with self._get_con().cursor() as cur:
            rows = cur.execute(
                """
                SELECT source,
                       EXTRACT(YEAR FROM update_date)::INT AS year,
                       COUNT(*) AS cnt
                FROM paper
                GROUP BY source, year
                ORDER BY source, year
                """
            ).fetchall()

        result: dict[str, dict[int, int]] = {}
        for source, year, cnt in rows:
            result.setdefault(source, {})[year] = cnt

        return result

    def count_papers_by_source(self):
        """Return a dict mapping each source to its paper count, plus a total."""
        with self._get_con().cursor() as cur:
            rows = cur.execute(
                """
                SELECT source, COUNT(*) AS cnt
                FROM paper
                GROUP BY source
                ORDER BY source
                """
            ).fetchall()

        result = {source: cnt for source, cnt in rows}
        result["total"] = sum(result.values())
        return result

    def commit(self) -> None:
        if self.con is not None:
            self.con.commit()

    def compute_similarity_over_time(
        self,
        embedding: list[float],
        similarity_threshold: float,
        filter_list: list[sql.Composable],
    ) -> list[tuple[Any, ...]]:
        if filter_list:
            or_group = sql.SQL(" OR ").join(
                sql.SQL("({})").format(flt) for flt in filter_list
            )
            filter_composed = sql.SQL("AND ({})").format(or_group)
        else:
            filter_composed = sql.SQL("")

        query = sql.SQL("""
                SELECT ps.update_date, (emb.embedding_gemini_embedding_001 <=> %s::halfvec(3072)) < %s AS is_similar
                FROM paper AS ps
                JOIN embedding AS emb
                  ON emb.paper_id = ps.paper_id
                WHERE emb.embedding_gemini_embedding_001 IS NOT NULL
                  {filter_str}
                ORDER BY update_date ASC
            """).format(filter_str=filter_composed)
        with self._get_con().cursor() as cur:
            rows = cur.execute(query, [embedding, similarity_threshold]).fetchall()

        return rows


if __name__ == "__main__":
    with PaperDatabase() as db:
        # papers = db.get_unembedded_conference_papers()
        db.summarise_current_conferences()
