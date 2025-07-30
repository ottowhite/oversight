from datetime import timedelta, datetime
from tqdm import tqdm
from ResearchListener import research_listeners
from SickleWrapper import SickleWrapper
from ArXivDBWrapper import ArXivDBWrapper
from EmbeddingModel import EmbeddingModel
from EmailSender import EmailSender
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
        self.email_sender = EmailSender("otto.white.apps@gmail.com")

    def __enter__(self):
        self.arxiv_db.__enter__()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.arxiv_db.__exit__(exc_type, exc_val, exc_tb)
        del self.email_sender
    
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

    def generate_digest_string(self, results, listener):
        output = ""
        output += f"Showing top {listener.num_papers} most similar papers to {listener.title} from the last day\n\n"
        for document_str, similarity in results:
            result = json.loads(document_str)
            paper_id = result["metadata"]["arXivRaw"]["id"]
            title = result["metadata"]["arXivRaw"]["title"]

            date = result["header"]["datestamp"]
            abstract = result["metadata"]["arXivRaw"]["abstract"]
            link = f"https://arxiv.org/abs/{paper_id}"

            # time_since_date = datetime.now() - datetime.strptime(date, "%Y-%m-%d")
            # days_since_date = time_since_date.days
            # if days_since_date < 30:
            #     time_since_date_str = f"{days_since_date} days ago"
            # elif days_since_date < 365:
            #     time_since_date_str = f"{days_since_date // 30} months ago"
            # else:
            #     time_since_date_str = f"{days_since_date // 365} years ago"

            # output += f"{title} ({date}) (similarity: {similarity:.4f}) (time since date: {time_since_date_str})\n"
            output += f"{title} (similarity: {similarity:.4f})\n"
            output += f"{abstract}\n"
            output += f"{link}\n"
            output += "\n"

        return output

    def generate_daily_digest(self, research_listeners):
        for listener in research_listeners:
            embedding = self.embedding_model.model.embed_query(listener.text)
            results = self.arxiv_db.generate_daily_digest(embedding, listener.num_papers)
            digest_string = self.generate_digest_string(results, listener)
            self.email_sender.send_email_multiple_recipients(listener.email_recipients, f"Daily research digest for {listener.title}", digest_string)

if __name__ == "__main__":
    with ArXivRepository("data/arxiv/arxiv_ai_papers.db", "models/gemini-embedding-001", overlap_timedelta=timedelta(days=1)) as repo:
        repo.generate_daily_digest(research_listeners)
