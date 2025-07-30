import duckdb
import json
from datetime import datetime
from tqdm import tqdm
from Paper import Paper

class ArXivDBWrapper:
    def __init__(self, db_path):
        self.db_path = db_path
        self.ai_categories = ["cs:cs:AI", "cs:cs:CL", "cs:cs:LG", "cs:cs:MA"]
        self.ai_categories_str = "(" + ",".join(f"'{category}'" for category in self.ai_categories) + ")"
        self.con = None
        self.date_format = "%Y-%m-%d"

    def __enter__(self):
        self.con = duckdb.connect(self.db_path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.con is not None:
            self.con.close()
            self.con = None
    
    def insert_paper(self, paper: Paper):
        self.con.execute("""
            INSERT INTO embedded_arxiv_documents (paper_id, document, update_date)
            VALUES (?, ?, ?)
            ON CONFLICT (paper_id) DO UPDATE
            SET document = EXCLUDED.document,
                update_date = EXCLUDED.update_date,
                embedding_gemini_embedding_001 = NULL
            WHERE embedded_arxiv_documents.update_date < EXCLUDED.update_date;
        """, [paper.paper_id, json.dumps(paper.document), paper.paper_date.strftime(self.date_format)])
    
    def is_updated(self, paper: Paper):
        return self.con.execute("""
            SELECT 1 FROM embedded_arxiv_documents
            WHERE paper_id = ?::VARCHAR AND update_date < ?::DATE
        """, [paper.paper_id, paper.paper_date.strftime(self.date_format)]).fetchone() is not None
    
    def is_new(self, paper: Paper):
        return self.con.execute("""
            SELECT 1 FROM embedded_arxiv_documents
            WHERE paper_id = ?::VARCHAR
        """, [paper.paper_id]).fetchone() is None

    def get_newest_date(self):
        return self.con.execute("SELECT MAX(update_date) FROM embedded_arxiv_documents").fetchone()[0]
    
    def try_update_categories(self, paper: Paper):
        stored_categories = self.con.execute("""
            SELECT category FROM paper_categories
            WHERE paper_id = ?::VARCHAR
        """, [paper.paper_id]).fetchall()
        stored_categories = {c[0] for c in stored_categories}

        if stored_categories == paper.categories:
            return False
        
        # Delete the existing categories
        self.con.execute("BEGIN TRANSACTION;")
        self.con.execute("""
            DELETE FROM paper_categories
            WHERE paper_id = ?::VARCHAR
        """, [paper.paper_id])

        # Add the new categories
        bulk_insertions = []
        for category in paper.categories:
            bulk_insertions.append((paper.paper_id, category))
        self.con.executemany("""
            INSERT INTO paper_categories (paper_id, category)
            VALUES (?, ?)
        """, bulk_insertions)
        self.con.execute("COMMIT;")

        return True
    
    def get_unembedded_ai_papers(self):
        return self.con.execute(f"""
            SELECT DISTINCT ps.paper_id, ps.document
            FROM embedded_arxiv_documents AS ps
            JOIN paper_categories AS pc
            ON ps.paper_id = pc.paper_id
            WHERE ps.embedding_gemini_embedding_001 IS NULL
            AND pc.category IN {self.ai_categories_str}
        """).fetchall()
    
    def count_rows_to_update_and_insert(self, papers: list[Paper]):
        total_updates = 0
        total_new = 0
        for paper in tqdm(papers, desc="Checking for paper updates and new papers", total=len(papers)):
            total_updates += self.is_updated(paper)
            total_new += self.is_new(paper)
        
        return total_updates, total_new

    
if __name__ == "__main__":
    with ArXivDBWrapper("data/arxiv/arxiv_ai_papers.db") as db:
        print(len(db.get_unembedded_ai_papers()))