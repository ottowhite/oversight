from datetime import datetime

class Paper:
    def __init__(
            self,
            paper_id: str,
            document: object,
            paper_date: datetime,
            categories: set[str],
            embedding_gemini_embedding_001: list[float] | None = None
    ):
        self.paper_id = paper_id
        self.document = document
        self.paper_date = paper_date
        self.categories = categories
        self.embedding_gemini_embedding_001 = embedding_gemini_embedding_001
