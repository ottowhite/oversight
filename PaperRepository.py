import json
import os
from tqdm import tqdm

from ArXivDBWrapper import ArXivDBWrapper
from Paper import Paper
from EmbeddingModel import EmbeddingModel

class PaperRepository:
    def __init__(self, embedding_model_name: str):
        self.db = ArXivDBWrapper()
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

if __name__ == "__main__":
    # repo.add_scraped_papers_from_dir("data/systems_conferences")
    # repo.add_openreview_papers_from_dir("data/openreview_conferences")

    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        repo.embed_missing_conference_papers()