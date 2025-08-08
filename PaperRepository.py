import json
import os
from tqdm import tqdm
from datetime import timedelta

from relevant_abstracts import *

from PaperDatabase import PaperDatabase
from Paper import Paper
from EmbeddingModel import EmbeddingModel
from ResearchLLM import ResearchLLM

class PaperRepository:
    def __init__(self, embedding_model_name: str):
        self.db = PaperDatabase()
        self.embedding_model = EmbeddingModel(embedding_model_name)

    def __enter__(self):
        self.db.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.__exit__(exc_type, exc_val, exc_tb)

    def add_scraped_papers(self, path: str):
        with open(path, "r") as f:
            papers_json = json.load(f)
        
        for paper_json in papers_json:
            paper = Paper.from_scraped_json(paper_json)
            self.db.insert_paper(paper)
    
    def add_openreview_papers(self, path: str, api_version: int):
        with open(path, "r") as f:
            papers_json = json.load(f)
        
        for paper_json in papers_json:
            paper = Paper.from_openreview_json(paper_json, api_version)
            self.db.insert_paper(paper)
    
    def add_scraped_papers_from_dir(self, path: str):
        for filename in tqdm(os.listdir(path), desc="Adding scraped conferences", total=len(os.listdir(path))):
            self.add_scraped_papers(os.path.join(path, filename))

    def add_openreview_papers_from_dir(self, path: str):
        for filename in tqdm(os.listdir(path), desc="Adding openreview conferences", total=len(os.listdir(path))):
            filename_no_ext = filename.split(".")[0]
            if filename_no_ext.endswith("_v1"):
                api_version = 1
            elif filename_no_ext.endswith("_v2"):
                api_version = 2
            else:
                raise ValueError(f"Invalid filename: {filename}")

            self.add_openreview_papers(os.path.join(path, filename), api_version)

    def embed_missing_conference_papers(self):
        papers_to_embed = self.db.get_unembedded_conference_papers()
        print(f"Embedding {len(papers_to_embed)} papers")

        paper_ids = []
        abstracts = []
        for paper_id, abstract in papers_to_embed:
            paper_ids.append(paper_id)
            abstracts.append(abstract)
            if abstract is None or abstract == "":
                breakpoint()

        for i, (embedding, paper_id) in tqdm(enumerate(zip(self.embedding_model.embed_documents_rate_limited(abstracts), paper_ids)), desc="Embedding papers", total=len(paper_ids)):
            self.db.update_embedding(paper_id, embedding)

            if i % 10 == 0:
                self.db.con.commit()
    
    def get_newest_related_papers(self, text: str, timedelta: timedelta, filter_list: list[str] | None = None, limit: int = 10):
        embedding = self.embedding_model.model.embed_query(text)
        paper_rows = self.db.get_newest_papers(embedding, timedelta, filter_list or [], limit)
        papers: list[Paper] = []
        for paper_row in paper_rows:
            paper = Paper.from_database_row(paper_row)
            papers.append(paper)
        return papers
    
    @staticmethod
    def build_filter_string(sources: list[str]):
        # Prefer a compact IN clause to avoid precedence issues
        sources_sql = ", ".join([f"'{s}'" for s in sources])
        return f"source IN ({sources_sql})"
    
if __name__ == "__main__":
    # repo.add_scraped_papers_from_dir("data/systems_conferences")
    # repo.add_openreview_papers_from_dir("data/openreview_conferences")

    if False:
        research_llm = ResearchLLM(model_name="openai/o3-mini")
        abstract = research_llm.generate_fake_abstract(
            "Inference-time scaling techniques for large language models, different types of searches such as beam search, MCTS, others, and their characteristics",
            "AI",
            "Paper"
        )
        print("Generated fake abstract:")
        print(abstract)
        print()
        print()
    else:
        abstract = "Recent advancements in large language models have spurred interest in inference-time scaling techniques to balance efficiency and performance. In this work, we analyze and integrate several search strategies—including beam search, Monte Carlo Tree Search (MCTS), and alternative approaches—to enhance the inference process. Our key contribution lies in a unified framework that dynamically selects optimal search techniques based on model characteristics and contextual constraints. Extensive experimentation on established benchmarks demonstrates significant improvements in both speed and output accuracy compared to standard search methods. We discuss theoretical underpinnings, implementation challenges, and potential avenues for future research in scalable inference algorithms via evaluation."

    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        ai_conference_filter = repo.build_filter_string(["ICML", "NeurIPS", "ICLR"])
        arxiv_filter = repo.build_filter_string(["arxiv"])
        systems_filter = repo.build_filter_string(["OSDI", "SOSP", "ASPLOS", "ATC", "NSDI", "MLSys", "EuroSys"])

        papers = repo.get_newest_related_papers(abstract, timedelta(days=365*5), [ai_conference_filter])
        for paper in papers:
            print(paper)
