from __future__ import annotations

from datetime import datetime
from tqdm import tqdm
from sickle import Sickle
import xmltodict
from Paper import Paper


class SickleWrapper:
    def __init__(
        self, base_url: str, arxiv_metadata_type: str, cs_set: str, date_format: str
    ) -> None:
        self.base_url = base_url
        self.arxiv_metadata_type = arxiv_metadata_type
        self.cs_set = cs_set
        self.date_format = date_format

    def get_new_papers(self, from_date: datetime) -> list[Paper]:
        sickle = Sickle(self.base_url)

        records = sickle.ListRecords(
            **{
                "metadataPrefix": self.arxiv_metadata_type,
                "set": self.cs_set,
                "ignore_deleted": True,  # skip withdrawn items
                "from": from_date.strftime(self.date_format),
            }
        )

        new_papers: list[Paper] = []
        for new_record in tqdm(records, desc="Parsing potentially new papers"):
            document = xmltodict.parse(new_record.raw)["record"]
            paper_id: str = document["metadata"]["arXivRaw"]["id"]
            revision_submission_date = datetime.strptime(
                document["header"]["datestamp"], self.date_format
            )
            link = f"https://arxiv.org/abs/{paper_id}"

            categories = document["header"]["setSpec"]
            if isinstance(categories, str):
                categories_set: set[str] = {categories}
            else:
                assert isinstance(categories, list), (
                    f"Categories is not a list: {categories}"
                )
                categories_set = {str(c) for c in categories}

            paper = Paper(
                paper_id=paper_id,
                document=document,
                abstract=document["metadata"]["arXivRaw"]["abstract"],
                title=document["metadata"]["arXivRaw"]["title"],
                source="arxiv",
                link=link,
                paper_date=revision_submission_date,
                categories=categories_set,
            )

            new_papers.append(paper)

        return new_papers
