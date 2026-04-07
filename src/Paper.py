from datetime import datetime
import json
import uuid

class Paper:
    def __init__(
            self,
            paper_id: str,
            document: object,
            paper_date: datetime,
            abstract: str,
            title: str,
            categories: set[str] | None = None,
            source: str | None = None,
            embedding_gemini_embedding_001: list[float] | None = None,
            link: str | None = None,
            time_since_date_str: str | None = None,
    ):
        assert title is not None
        assert abstract is not None
        assert paper_id is not None
        assert paper_date is not None
        assert document is not None

        self.paper_id = paper_id
        self.document = document
        self.paper_date = paper_date
        self.categories = categories
        self.embedding_gemini_embedding_001 = embedding_gemini_embedding_001
        self.abstract = abstract
        self.link = link
        self.time_since_date_str = time_since_date_str
        self.title = title
        self.source = source
    
    def __str__(self):
        time_since_date = datetime.now().date() - self.paper_date
        days_since_date = time_since_date.days

        years_since_date = days_since_date // 365
        months_since_date = (days_since_date % 365) // 30
        days_since_date = days_since_date % 30

        years_str = f"{years_since_date} years " if years_since_date > 0 else ""
        months_str = f"{months_since_date} months " if months_since_date > 0 else ""
        days_str = f"{days_since_date} days " if months_str == "" and years_str == "" else ""

        time_since_date_str = f"{years_str}{months_str}{days_str}ago"

        output = f"{self.title} ({time_since_date_str}, {self.source}) \n"
        output += f"{self.abstract} \n"
        output += f"{self.link} \n"

        return output

    @staticmethod
    def date_format():
        return "%Y-%m-%d"

    @staticmethod
    def from_document(document: object):

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
    
    @staticmethod
    def from_scraped_json(paper_json: dict):
        return Paper(
            paper_id=paper_json["paper_id"],
            document=paper_json,
            title=paper_json["title"],
            abstract=paper_json["abstract"],
            paper_date=datetime.strptime(paper_json["date"], Paper.date_format()),
            link=paper_json["link"],
            source=paper_json["conference_name"]
        )
    
    @staticmethod
    def from_openreview_json(paper_json: dict, api_version: int):
        if api_version == 1:
            abstract = Paper.remove_null_bytes(paper_json["content"]["abstract"])
            title = Paper.remove_null_bytes(paper_json["content"]["title"])
        elif api_version == 2:
            abstract = Paper.remove_null_bytes(paper_json["content"]["abstract"]["value"])
            title = Paper.remove_null_bytes(paper_json["content"]["title"]["value"])
        else:
            raise ValueError(f"Invalid API version: {api_version}")
        
        paper_date = datetime.strptime(paper_json["oversight_metadata"]["conference_date"], Paper.date_format())
        source = paper_json["oversight_metadata"]["conference_name"]
        return Paper(
            paper_id=paper_json["id"],
            document=Paper.remove_null_bytes(paper_json),
            title=title,
            abstract=abstract,
            paper_date=paper_date,
            source=source
        )
    
    @staticmethod
    def from_database_row(row: tuple):
        (uuid, created_at, paper_id, document, update_date, embedding_gemini_embedding_001, source, abstract, title, link, similarity) = row

        paper = Paper(
            paper_id=paper_id,
            document=document,
            title=title,
            abstract=abstract,
            paper_date=update_date,
            source=source,
            link=link
        )

        return paper, similarity

    @staticmethod
    def remove_null_bytes(obj):
        if isinstance(obj, str):
            return obj.replace('\x00', '')
        elif isinstance(obj, dict):
            return {k: Paper.remove_null_bytes(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Paper.remove_null_bytes(v) for v in obj]
        else:
            return obj
