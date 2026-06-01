from __future__ import annotations

import json
import os
from tqdm import tqdm
from datetime import timedelta
from psycopg import sql

from .PaperDatabase import PaperDatabase
from .Paper import Paper
from .EmbeddingModel import EmbeddingModel
from .ResearchLLM import ResearchLLM


class PaperRepository:
    def __init__(self, embedding_model_name: str) -> None:
        self.db = PaperDatabase()
        self.embedding_model = EmbeddingModel(embedding_model_name)

    def __enter__(self) -> PaperRepository:
        self.db.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        self.db.__exit__(exc_type, exc_val, exc_tb)

    def add_scraped_papers(self, path: str) -> None:
        with open(path, "r") as f:
            papers_json = json.load(f)

        for paper_json in papers_json:
            paper = Paper.from_scraped_json(paper_json)
            updated_rows, new_rows, skipped_rows = self.db.insert_paper(paper)

    def add_openreview_papers(self, path: str, api_version: int) -> None:
        with open(path, "r") as f:
            papers_json = json.load(f)

        for paper_json in papers_json:
            paper = Paper.from_openreview_json(paper_json, api_version)
            updated_rows, new_rows, skipped_rows = self.db.insert_paper(paper)

    def add_scraped_papers_from_dir(self, path: str) -> None:
        for filename in tqdm(
            os.listdir(path),
            desc="Adding scraped conferences",
            total=len(os.listdir(path)),
        ):
            self.add_scraped_papers(os.path.join(path, filename))

    def add_openreview_papers_from_dir(self, path: str) -> None:
        for filename in tqdm(
            os.listdir(path),
            desc="Adding openreview conferences",
            total=len(os.listdir(path)),
        ):
            filename_no_ext = filename.split(".")[0]
            if filename_no_ext.endswith("_v1"):
                api_version = 1
            elif filename_no_ext.endswith("_v2"):
                api_version = 2
            else:
                raise ValueError(f"Invalid filename: {filename}")

            self.add_openreview_papers(os.path.join(path, filename), api_version)

    def embed_missing_conference_papers(self) -> None:
        papers_to_embed = self.db.get_unembedded_conference_papers()
        print(f"Embedding {len(papers_to_embed)} papers")

        paper_ids: list[str] = []
        abstracts: list[str] = []
        for paper_id, abstract in papers_to_embed:
            paper_ids.append(paper_id)
            abstracts.append(abstract)
            if abstract is None or abstract == "":
                breakpoint()

        for i, (embedding, paper_id) in tqdm(
            enumerate(
                zip(
                    self.embedding_model.embed_documents_rate_limited(abstracts),
                    paper_ids,
                )
            ),
            desc="Embedding papers",
            total=len(paper_ids),
        ):
            self.db.update_embedding(paper_id, embedding)

            if i % 10 == 0:
                self.db._get_con().commit()

    def get_newest_related_papers(
        self,
        text: str,
        timedelta: timedelta,
        filter_list: list[sql.Composable] | None = None,
        limit: int = 10,
        ef_search: int = 40,
    ) -> list[Paper]:
        embedding = self.embedding_model.model.embed_query(text)
        paper_rows = self.db.get_newest_papers(
            embedding, timedelta, filter_list or [], limit, ef_search=ef_search
        )
        papers: list[Paper] = []
        for paper_row in paper_rows:
            paper, similarity = Paper.from_database_row(paper_row)
            papers.append(paper)
        return papers

    def get_neighbors(
        self,
        paper_id: str,
        k: int,
        mutual: bool = False,
        ef_search: int = 80,
    ) -> list[tuple[Paper, float]]:
        """Return the kNN of ``paper_id`` as ``[(Paper, similarity), ...]``.

        Hydrates each neighbor via a single bulk fetch from the ``paper`` table,
        preserving the similarity ordering returned by ``find_neighbors``.
        """
        neighbors = self.db.find_neighbors(
            paper_id, k=k, mutual=mutual, ef_search=ef_search
        )
        if not neighbors:
            return []

        sim_by_id = {pid: sim for pid, sim in neighbors}
        rows = self.db.get_papers_by_ids([pid for pid, _ in neighbors])
        results: list[tuple[Paper, float]] = []
        for row in rows:
            paper, _ = Paper.from_database_row(row)
            results.append((paper, sim_by_id[paper.paper_id]))
        # Restore the similarity-sorted order (descending).
        results.sort(key=lambda pair: pair[1], reverse=True)
        return results

    def get_paper(self, paper_id: str) -> Paper | None:
        """Fetch a single Paper by id, or ``None`` if it isn't in the DB."""
        rows = self.db.get_papers_by_ids([paper_id])
        if not rows:
            return None
        paper, _ = Paper.from_database_row(rows[0])
        return paper

    def compute_similarity_over_time(
        self,
        text: str,
        similarity_threshold: float,
        filter_list: list[sql.Composable] | None = None,
    ) -> tuple[list[object], list[int], list[float]]:
        embedding = self.embedding_model.model.embed_query(text)
        rows = self.db.compute_similarity_over_time(
            embedding, similarity_threshold, filter_list or []
        )
        cumulative_similar = 0
        cumulative_similarities: list[int] = []
        cumulative_similarities_weighted: list[float] = []
        dates: list[object] = []
        for i, (update_date, is_similar) in enumerate(rows):
            dates.append(update_date)
            cumulative_similar += is_similar
            cumulative_similarities.append(cumulative_similar)
            cumulative_similarities_weighted.append(cumulative_similar / (i + 1))

        return dates, cumulative_similarities, cumulative_similarities_weighted

    @staticmethod
    def build_filter_sql(sources: list[str]) -> sql.Composed:
        if len(sources) == 1:
            return sql.SQL("ps.source = {}").format(sql.Literal(sources[0]))
        return sql.SQL("ps.source IN ({})").format(
            sql.SQL(", ").join(sql.Literal(s) for s in sources)
        )


if __name__ == "__main__":
    # with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
    #     repo.add_scraped_papers_from_dir("data/vldb")
    #     repo.embed...

    # repo.add_openreview_papers_from_dir("data/openreview_conferences")

    if False:
        research_llm = ResearchLLM(model_name="openai/o3-mini")
        abstract = research_llm.generate_fake_abstract(
            "Inference-time scaling techniques for large language models, different types of searches such as beam search, MCTS, others, and their characteristics",
            "AI",
            "Paper",
        )
        print("Generated fake abstract:")
        print(abstract)
        print()
        print()
    else:
        abstract = "Recent advancements in large language models have spurred interest in inference-time scaling techniques to balance efficiency and performance. In this work, we analyze and integrate several search strategies—including beam search, Monte Carlo Tree Search (MCTS), and alternative approaches—to enhance the inference process. Our key contribution lies in a unified framework that dynamically selects optimal search techniques based on model characteristics and contextual constraints. Extensive experimentation on established benchmarks demonstrates significant improvements in both speed and output accuracy compared to standard search methods. We discuss theoretical underpinnings, implementation challenges, and potential avenues for future research in scalable inference algorithms via evaluation."

    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        ai_conference_filter = repo.build_filter_sql(["ICML", "NeurIPS", "ICLR"])
        arxiv_filter = repo.build_filter_sql(["arxiv"])
        systems_filter = repo.build_filter_sql(
            ["OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys"]
        )

        papers = repo.get_newest_related_papers(
            abstract, timedelta(days=365 * 5), [repo.build_filter_sql(["VLDB"])]
        )
        for paper in papers:
            print(paper)
