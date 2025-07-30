from datetime import timedelta
from tqdm import tqdm
from SickleWrapper import SickleWrapper
from ArXivDBWrapper import ArXivDBWrapper
from EmbeddingModel import EmbeddingModel
import json

# Database backup example
# EXPORT DATABASE 'target_directory' (
#     FORMAT parquet,
#     COMPRESSION zstd,
#     ROW_GROUP_SIZE 100_000
# );

# IMPORT DATABASE 'source_directory';


class ArXivRepository:
    def __init__(self, db_path, embedding_model_name, overlap_timedelta: timedelta = timedelta(days=1)):
        self.db_path = db_path
        self.overlap_timedelta = overlap_timedelta
        self.arxiv_db = ArXivDBWrapper(db_path)
        self.embedding_model = EmbeddingModel(embedding_model_name)
        self.sickle = SickleWrapper(
            base_url="https://oaipmh.arxiv.org/oai",
            arxiv_metadata_type="arXivRaw",
            cs_set="cs:cs",
            date_format="%Y-%m-%d"
        )

    def __enter__(self):
        self.arxiv_db.__enter__()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.arxiv_db.__exit__(exc_type, exc_val, exc_tb)
    
    def sync(self):
        newest_date = self.arxiv_db.get_newest_date()
        from_date = newest_date - self.overlap_timedelta
        print(f"Syncing from {from_date} to avoid missed papers")
        self._sync_from_date(from_date)
        self._embed_missing_ai_papers()

    def _sync_from_date(self, from_date):
        new_papers = self.sickle.get_new_papers(from_date)

        total_updates, total_new = self.arxiv_db.count_rows_to_update_and_insert(new_papers)
        print(f"{total_updates} papers to update, and {total_new} new papers to insert")

        for paper in tqdm(new_papers, desc="Inserting new and updated papers", total=len(new_papers)):
            self.arxiv_db.insert_paper(paper)
            self.arxiv_db.try_update_categories(paper)
    
    def _embed_missing_ai_papers(self):
        papers_to_embed = self.arxiv_db.get_unembedded_ai_papers()
        print(f"Embedding {len(papers_to_embed)} papers")

        paper_ids = []
        abstracts = []
        for paper_id, document_str in tqdm(papers_to_embed, desc="Parsing papers", total=len(papers_to_embed)):
            paper_ids.append(paper_id)
            document = json.loads(document_str)
            abstract = document["metadata"]["arXivRaw"]["abstract"]
            abstracts.append(abstract)

        for embedding, paper_id in tqdm(zip(self.embedding_model.embed_documents_rate_limited(abstracts), paper_ids), desc="Embedding papers", total=len(paper_ids)):
            self.arxiv_db.update_embedding(paper_id, embedding)

if __name__ == "__main__":
    with ArXivRepository("data/arxiv/arxiv_ai_papers.db", "models/gemini-embedding-001", overlap_timedelta=timedelta(days=1)) as repo:
        repo.sync()
