from datetime import timedelta
from tqdm import tqdm
from SickleWrapper import SickleWrapper
from ArXivDBWrapper import ArXivDBWrapper

# Database backup example
# EXPORT DATABASE 'target_directory' (
#     FORMAT parquet,
#     COMPRESSION zstd,
#     ROW_GROUP_SIZE 100_000
# );

# IMPORT DATABASE 'source_directory';


class ArXivRepositoryDB:
    def __init__(self, db_path, overlap_timedelta: timedelta = timedelta(days=1)):
        self.db_path = db_path
        self.overlap_timedelta = overlap_timedelta
        self.arxiv_db = ArXivDBWrapper(db_path)
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

    def _sync_from_date(self, from_date):
        new_papers = self.sickle.get_new_papers(from_date)

        total_updates, total_new = self.arxiv_db.count_rows_to_update_and_insert(new_papers)
        print(f"{total_updates} papers to update, and {total_new} new papers to insert")

        for paper in tqdm(new_papers, desc="Inserting new and updated papers", total=len(new_papers)):
            self.arxiv_db.insert_paper(paper)
            self.arxiv_db.try_update_categories(paper)


if __name__ == "__main__":
    with ArXivRepositoryDB("data/arxiv/arxiv_ai_papers.db", overlap_timedelta=timedelta(days=1)) as repo:
        repo.sync()
        