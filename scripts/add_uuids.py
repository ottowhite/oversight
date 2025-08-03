import os
import json
import uuid

# get every filename in data/systems_conferences
for filename in os.listdir("data/systems_conferences"):
    with open(f"data/systems_conferences/{filename}", "r") as f:
        papers_json = json.load(f)
    
    for paper_json in papers_json:
        if "paper_id" not in paper_json:
            paper_json["paper_id"] = str(uuid.uuid4())

    with open(f"data/systems_conferences/{filename}", "w") as f:
        json.dump(papers_json, f, indent=2, ensure_ascii=False)