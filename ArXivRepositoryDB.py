import duckdb
from datetime import datetime, timedelta
from tqdm import tqdm
from sickle import Sickle
import xmltodict
import json
from ArXivDBWrapper import ArXivDBWrapper
from Paper import Paper

# Database backup example
# EXPORT DATABASE 'target_directory' (
#     FORMAT parquet,
#     COMPRESSION zstd,
#     ROW_GROUP_SIZE 100_000
# );

# IMPORT DATABASE 'source_directory';


class ArXivRepositoryDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.date_format = "%Y-%m-%d"
        self.base_url = "https://oaipmh.arxiv.org/oai"       
        self.cs_set = "cs:cs"                              
        self.arxiv_metadata_type = "arXivRaw"                              
        self.arxiv_db = ArXivDBWrapper(db_path)

    def __enter__(self):
        self.arxiv_db.__enter__()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.arxiv_db.__exit__(exc_type, exc_val, exc_tb)
    
    def sync(self):
        newest_date = self.arxiv_db.get_newest_date()
        from_date = (newest_date - timedelta(days=1))
        print(f"Syncing from {from_date} to avoid missed papers")

        self._sync_from_date(from_date)

    def _sync_from_date(self, from_date):
        sickle = Sickle(self.base_url)

        records = sickle.ListRecords(**{
            'metadataPrefix': self.arxiv_metadata_type,
            'set': self.cs_set,
            'ignore_deleted': True, # skip withdrawn items
            'from': from_date.strftime(self.date_format)
        })

        new_papers: list[Paper] = []
        for new_record in tqdm(records, desc="Parsing potentially new papers"):
            document = xmltodict.parse(new_record.raw)['record']
            paper_id = document['metadata']['arXivRaw']['id']
            revision_submission_date = datetime.strptime(document['header']['datestamp'], self.date_format)

            categories = document['header']['setSpec']
            if type(categories) == str:
                categories = set([categories])
            else:
                assert type(categories) == list, f"Categories is not a list: {categories}"
                categories = set(categories)

            paper = Paper(
                paper_id=paper_id,
                document=document,
                paper_date=revision_submission_date,
                categories=categories,
            )

            new_papers.append(paper)

        total_updates, total_new = self.arxiv_db.count_rows_to_update_and_insert(new_papers)
        print(f"{total_updates} papers to update, and {total_new} new papers to insert")

        for paper in tqdm(new_papers, desc="Inserting new and updated papers", total=len(new_papers)):
            self.arxiv_db.insert_paper(paper)
            self.arxiv_db.try_update_categories(paper)
        

if __name__ == "__main__":
    with ArXivRepositoryDB("data/arxiv/arxiv_ai_papers.db") as repo:
        repo.sync()
        