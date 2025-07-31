from datetime import datetime
import json

class Paper:
    def __init__(
            self,
            paper_id: str,
            document: object,
            paper_date: datetime,
            categories: set[str],
            embedding_gemini_embedding_001: list[float] | None = None,
            abstract: str | None = None,
            link: str | None = None,
            time_since_date_str: str | None = None,
            title: str | None = None
    ):
        self.paper_id = paper_id
        self.document = document
        self.paper_date = paper_date
        self.categories = categories
        self.embedding_gemini_embedding_001 = embedding_gemini_embedding_001
        self.abstract = abstract
        self.link = link
        self.time_since_date_str = time_since_date_str
        self.title = title

    @staticmethod
    def date_format():
        return "%Y-%m-%d"

    @staticmethod
    def from_document_str(document_str: str):
        document = json.loads(document_str)

        categories = document["header"]["setSpec"]
        if isinstance(categories, str):
            categories = [categories]
        else:
            assert isinstance(categories, list)
        categories = set(categories)

        paper_date = datetime.strptime(document["header"]["datestamp"], Paper.date_format())

        time_since_date = datetime.now() - paper_date
        days_since_date = time_since_date.days
        if days_since_date < 30:
            time_since_date_str = f"{days_since_date} days ago"
        elif days_since_date < 365:
            time_since_date_str = f"{days_since_date // 30} months ago"
        else:
            time_since_date_str = f"{days_since_date // 365} years ago"
        
        embedding = document["embedding_gemini_embedding_001"] if "embedding_gemini_embedding_001" in document else None

        return Paper(
            paper_id=document["metadata"]["arXivRaw"]["id"],
            document=document,
            paper_date=paper_date,
            categories=categories,
            embedding_gemini_embedding_001=embedding,
            abstract=document["metadata"]["arXivRaw"]["abstract"],
            link=f"https://arxiv.org/abs/{document['metadata']['arXivRaw']['id']}",
            time_since_date_str=time_since_date_str,
            title=document["metadata"]["arXivRaw"]["title"]
        )

