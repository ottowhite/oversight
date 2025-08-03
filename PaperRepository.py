import json
import os
from tqdm import tqdm

from ArXivDBWrapper import ArXivDBWrapper
from Paper import Paper

class PaperRepository:
    def __init__(self):
        self.db = ArXivDBWrapper()

    def __enter__(self):
        self.db.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.__exit__(exc_type, exc_val, exc_tb)

    def add_scraped_papers(self, path: str):
        with open(path, "r") as f:
            papers_json = json.load(f)
        
        for paper_json in papers_json:
            paper = Paper.from_scraped_json(paper_json)
            self.db.insert_paper(paper)
    
    def add_openreview_papers(self, path: str, api_version: int):
        with open(path, "r") as f:
            papers_json = json.load(f)
        
        for paper_json in papers_json:
            paper = Paper.from_openreview_json(paper_json, api_version)
            self.db.insert_paper(paper)
    
    def add_scraped_papers_from_dir(self, path: str):
        for filename in tqdm(os.listdir(path), desc="Adding scraped conferences", total=len(os.listdir(path))):
            self.add_scraped_papers(os.path.join(path, filename))

    def add_openreview_papers_from_dir(self, path: str):
        for filename in tqdm(os.listdir(path), desc="Adding openreview conferences", total=len(os.listdir(path))):
            filename_no_ext = filename.split(".")[0]
            if filename_no_ext.endswith("_v1"):
                api_version = 1
            elif filename_no_ext.endswith("_v2"):
                api_version = 2
            else:
                raise ValueError(f"Invalid filename: {filename}")

            self.add_openreview_papers(os.path.join(path, filename), api_version)

if __name__ == "__main__":
    with PaperRepository() as repo:
        # repo.add_scraped_papers_from_dir("data/systems_conferences")
        # repo.add_openreview_papers_from_dir("data/openreview_conferences")