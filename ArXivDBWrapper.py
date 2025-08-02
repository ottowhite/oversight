import json
from tqdm import tqdm
from Paper import Paper
from datetime import datetime, timedelta
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
import os

class ArXivDBWrapper:
    def __init__(self):
        load_dotenv()
        assert os.getenv("POSTGRES_USER") is not None, "Postgres user is not set"
        assert os.getenv("POSTGRES_PASSWORD") is not None, "Postgres password is not set"
        self.ai_categories = ["cs:cs:AI", "cs:cs:CL", "cs:cs:LG", "cs:cs:MA"]
        self.ai_categories_str = "(" + ",".join(f"'{category}'" for category in self.ai_categories) + ")"
        self.con = None
        self.date_format = "%Y-%m-%d"

    def __enter__(self):
        self.con = psycopg.connect(
            f"host=localhost dbname=oversight user={os.getenv('POSTGRES_USER')} password={os.getenv('POSTGRES_PASSWORD')}"
        )
        register_vector(self.con)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # NOTE: The commit only happens at the very end, and if there was an error, we will not commit.
        if self.con is not None:
            if exc_type is None:
                self.con.commit()
            else:
                print(f"Error committing transaction:\n{exc_value}")

            self.con.close()
            self.con = None

    def insert_paper(self, paper: Paper):
        with self.con.cursor() as cur:
            cur.execute("""
                INSERT INTO paper (paper_id, document, update_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (paper_id) DO UPDATE
                SET document = EXCLUDED.document,
                    update_date = EXCLUDED.update_date,
                    embedding_gemini_embedding_001 = NULL
                WHERE paper.update_date < EXCLUDED.update_date;
            """, [paper.paper_id, json.dumps(paper.document), paper.paper_date.strftime(self.date_format)])
    
    def is_updated(self, paper: Paper):
        with self.con.cursor() as cur:
            return cur.execute("""
                SELECT 1 FROM paper
                WHERE paper_id = %s::VARCHAR AND update_date < %s::DATE
            """, [paper.paper_id, paper.paper_date.strftime(self.date_format)]).fetchone() is not None
    
    def is_new(self, paper: Paper):
        with self.con.cursor() as cur:
            return cur.execute("""
                SELECT 1 FROM paper
                WHERE paper_id = %s::VARCHAR
            """, [paper.paper_id]).fetchone() is None

    def get_newest_date(self):
        with self.con.cursor() as cur:
            return cur.execute("SELECT MAX(update_date) FROM paper").fetchone()[0]
    
    def try_update_categories(self, paper: Paper):
        with self.con.cursor() as cur:
            stored_categories = cur.execute("""
                SELECT category FROM arxiv_paper_categories
                WHERE paper_id = %s::VARCHAR
            """, [paper.paper_id]).fetchall()
            stored_categories = {c[0] for c in stored_categories}

            if stored_categories == paper.categories:
                return False
        
            # Delete the existing categories
            cur.execute("""
                DELETE FROM arxiv_paper_categories
                WHERE paper_id = %s::VARCHAR
            """, [paper.paper_id])

            # Add the new categories
            bulk_insertions = []
            for category in paper.categories:
                bulk_insertions.append((paper.paper_id, category))
            cur.executemany("""
                INSERT INTO arxiv_paper_categories (paper_id, category)
                VALUES (%s, %s)
            """, bulk_insertions)

        return True
    
    def get_unembedded_ai_papers(self):
        with self.con.cursor() as cur:
            return cur.execute(f"""
                SELECT DISTINCT ps.paper_id, ps.document
                FROM paper AS ps
                JOIN arxiv_paper_categories AS pc
                ON ps.paper_id = pc.paper_id
                WHERE ps.embedding_gemini_embedding_001 IS NULL
                AND pc.category IN {self.ai_categories_str}
            """).fetchall()
    
    def update_embedding(self, paper_id: str, embedding: list[float]):
        with self.con.cursor() as cur:
            cur.execute("""
                UPDATE paper
                SET embedding_gemini_embedding_001 = %s::vector(3072)
                WHERE paper_id = %s::VARCHAR
            """, [embedding, paper_id])
    
    def count_rows_to_update_and_insert(self, papers: list[Paper]):
        total_updates = 0
        total_new = 0
        for paper in tqdm(papers, desc="Checking for paper updates and new papers", total=len(papers)):
            total_updates += self.is_updated(paper)
            total_new += self.is_new(paper)
        
        return total_updates, total_new
    
    def generate_daily_digest(self, embedding: list[float], limit: int = 10):
        last_day = datetime.now() - timedelta(days=2)
        with self.con.cursor() as cur:
            rows = cur.execute(f"""
                SELECT document, embedding_gemini_embedding_001 <-> %s::vector(3072) AS similarity
                FROM paper
                WHERE update_date > %s::DATE
                ORDER BY similarity ASC
                LIMIT %s
            """, [embedding, last_day, limit]).fetchall()

        return rows
    
    def time_filtered_k_nearest(self, embedding: list[float], timedelta: timedelta | None, limit: int):
        if timedelta is not None:
            oldest_time = (datetime.now() - timedelta).strftime("%Y-%m-%d")
            time_filter = f"WHERE update_date > '{oldest_time}'"
        else:
            time_filter = ""

        with self.con.cursor() as cur:
            return cur.execute(f"""
                SELECT document, embedding_gemini_embedding_001 <-> %s::vector(3072) AS similarity
                FROM paper
                {time_filter}
                ORDER BY similarity ASC
                LIMIT %s::INTEGER
            """, [embedding, limit]).fetchall()

if __name__ == "__main__":
    with ArXivDBWrapper() as db:
        print(len(db.get_unembedded_ai_papers()))