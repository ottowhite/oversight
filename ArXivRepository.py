from datetime import timedelta, datetime
import argparse
from tqdm import tqdm
from ResearchListener import research_listener_group, test_research_listener_group
from SickleWrapper import SickleWrapper
from PaperDatabase import PaperDatabase
from EmbeddingModel import EmbeddingModel
from EmailSender import EmailSender
from utils import get_logger
import json
from Paper import Paper
from ResearchLLM import ResearchLLM

# Database backup example
# EXPORT DATABASE 'target_directory' (
#     FORMAT parquet,
#     COMPRESSION zstd,
#     ROW_GROUP_SIZE 100_000
# );

# IMPORT DATABASE 'source_directory';

logger = get_logger()

class ArXivRepository:
    def __init__(self, embedding_model_name, research_llm_model_name: str, overlap_timedelta: timedelta = timedelta(days=1)):
        self.overlap_timedelta = overlap_timedelta
        self.arxiv_db = PaperDatabase()
        self.embedding_model = EmbeddingModel(embedding_model_name)
        self.research_llm = ResearchLLM(research_llm_model_name)
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
        logger.info(f"Syncing from {from_date} to avoid missed papers")
        self._sync_from_date(from_date)
        self._embed_missing_ai_papers()

    def _sync_from_date(self, from_date):
        new_papers = self.sickle.get_new_papers(from_date)

        total_updates, total_new = self.arxiv_db.count_rows_to_update_and_insert(new_papers)
        logger.info(f"{total_updates} papers to update, and {total_new} new papers to insert")

        for paper in tqdm(new_papers, desc="Inserting new and updated papers", total=len(new_papers)):
            self.arxiv_db.insert_paper(paper)
            self.arxiv_db.try_update_categories(paper)
    
    def _embed_missing_ai_papers(self):
        papers_to_embed = self.arxiv_db.get_unembedded_arxiv_ai_papers()
        logger.info(f"Embedding {len(papers_to_embed)} papers")

        paper_ids = []
        abstracts = []
        for paper_id, document in tqdm(papers_to_embed, desc="Parsing papers", total=len(papers_to_embed)):
            paper_ids.append(paper_id)
            abstract = document["metadata"]["arXivRaw"]["abstract"]
            abstracts.append(abstract)

        for embedding, paper_id in tqdm(zip(self.embedding_model.embed_documents_rate_limited(abstracts), paper_ids), desc="Embedding papers", total=len(paper_ids)):
            self.arxiv_db.update_embedding(paper_id, embedding)

    def generate_digest_string(self, results, include_time_since=False, include_similarity=True, include_date=True, include_link=True):
        output = ""
        # output += f"Showing top {num_papers} most similar papers to {title} from the last day\n\n"
        for document, similarity in results:
            paper = Paper.from_document(document)

            output += f"{paper.title}"
            output += f" ({paper.paper_date})" if include_date else ""
            output += f" (similarity: {similarity:.4f})" if include_similarity else ""
            output += f" (time since date: {paper.time_since_date_str})" if include_time_since else ""
            output += f"\n"
            output += f"{paper.abstract}\n"
            output += f"{paper.link}" if include_link else ""
            output += "\n\n"

        return output
    
    def _print_time_filtered_digest(self, embedding, timedelta, limit):
        results = self.arxiv_db.time_filtered_k_nearest(embedding, timedelta=timedelta, limit=limit)
        digest = self.generate_digest_string(results, include_time_since=True, include_similarity=True, include_date=False, include_link=True)
        print(f"Showing top {limit} most similar papers from the last {timedelta.days if timedelta is not None else 'all time'}")
        print(digest)
        print("\n")
    
    def print_time_filtered_digests(self, query):
        embedding = self.embedding_model.model.embed_query(query)

        self._print_time_filtered_digest(embedding, timedelta(days=30), 10)
        print("--------------------------------------------------------------------")
        self._print_time_filtered_digest(embedding, timedelta(days=30*6), 15)
        print("--------------------------------------------------------------------")
        self._print_time_filtered_digest(embedding, timedelta(days=365), 20)
        print("--------------------------------------------------------------------")
        self._print_time_filtered_digest(embedding, None, 30)

    def email_daily_digest(self, research_listener_group):
        paper_similarities = []
        for listener in research_listener_group.research_listeners:
            embedding = self.embedding_model.model.embed_query(listener.text)
            rows = self.arxiv_db.generate_daily_digest(embedding, research_listener_group.num_papers)
            for document, similarity in rows:
                paper_similarities.append((listener.title, Paper.from_document(document), similarity))
        
        # sort by ascending similarity
        paper_similarities.sort(key=lambda result: result[2])
        seen_titles = set()
        paper_similarities_unique = []
        for listener_title_name, paper, similarity in paper_similarities:
            if paper.title in seen_titles:
                continue
                
            seen_titles.add(paper.title)
            paper_similarities_unique.append((listener_title_name, paper, similarity))
        
        paper_similarities_truncated = paper_similarities_unique[:research_listener_group.num_papers]

        digest_string = self.generate_daily_digest_string(paper_similarities_truncated)
        self.email_sender.send_email_multiple_recipients(research_listener_group.email_recipients, f"Daily research digest for {research_listener_group.title}", digest_string)
    
    def generate_daily_digest_string(self, paper_similarities):
        digest_string = ""
        for listener_title, paper, similarity in paper_similarities:
            digest_string += f"{paper.title} (most related to {listener_title}): {similarity:.3f}\n\n"
            digest_string += f"{paper.abstract}\n"
            digest_string += f"{paper.link}\n\n"
            digest_string += f"{self.research_llm.generate_relatedness_summary(paper.abstract)}\n\n"
            digest_string += "------------------------------------------------\n\n"

        return digest_string

if __name__ == "__main__":
    # parse flags for differnet modes
    parser = argparse.ArgumentParser()
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--query", action="store_true")
    parser.add_argument("--no-sync", action="store_true", default=False)
    args = parser.parse_args()

    if not args.digest and not args.query:
        print("Must use either --digest or --query")
        exit(1)

    if args.digest and args.query:
        print("Cannot use both digest and query mode at the same time")
        exit(1)

    with ArXivRepository(
        embedding_model_name="models/gemini-embedding-001",
        research_llm_model_name="google/gemini-2.5-flash",
        overlap_timedelta=timedelta(days=1)
    ) as repo:
        if args.digest:
            if not args.no_sync:
                repo.sync()
            else:
                logger.info("Skipping sync")

            repo.email_daily_digest(research_listener_group)
        elif args.query:
            query_str = "Large-scale language-model (LM) applications now resemble distributed programs whose interactive “agentic” workflows are governed by service-level objectives (SLOs) that users experience at sub-second granularity. Existing schedulers optimise only the end-to-end deadline of the entire LM program, ignoring the time-between-consumable chunks (TBC) that determines perceived responsiveness and opportunities to cancel misbehaving runs. We present SCALE (SLO-Conscious Adaptive Latency-and-Efficiency scheduler), the first runtime that jointly optimises throughput and fine-grained latency for LM programs. SCALE models each program component—including conditional branches—and predicts its execution time on heterogeneous accelerators. Given a per-component SLO budget, SCALE formulates scheduling as a constrained optimisation that maximises global throughput while guaranteeing that every TBC (and, optionally, the overall deadline) is met. A prototype of SCALE deployed on a 128-GPU cluster supports both inference-time agent workflows and training-time self-reflection loops. Across nine production-style LM workloads, SCALE sustains up to 2.3× higher job throughput than a latency-agnostic baseline while meeting 99.9 % of TBC SLOs; compared with an end-to-end-only SLO scheduler, it reduces median interactive latency by up to 4.7× without losing cluster utilisation. These results demonstrate that SLO-aware, mixed latency/throughput optimisation is essential for the next generation of LM systems, providing a complete picture for both end users and datacentre operators."
            repo.print_time_filtered_digests(query_str)
