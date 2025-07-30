from datetime import datetime
from tqdm import tqdm
from sickle import Sickle
import xmltodict
from Paper import Paper

class SickleWrapper:
    def __init__(self, base_url: str, arxiv_metadata_type: str, cs_set: str, date_format: str):
        self.base_url = base_url
        self.arxiv_metadata_type = arxiv_metadata_type
        self.cs_set = cs_set
        self.date_format = date_format

    def get_new_papers(self, from_date: datetime) -> list[Paper]:
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

        return new_papers