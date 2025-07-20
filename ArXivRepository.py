import xmltodict
from datetime import datetime, timedelta
from sickle import Sickle
import os
import json
from collections import OrderedDict

class ArXivRepository:
    def __init__(self, xml_data_path, json_ai_papers_path):
        self.xml_data_path = xml_data_path
        self.json_ai_papers_path = json_ai_papers_path
        self.date_format = "%Y-%m-%d"
        self.base_url = "https://oaipmh.arxiv.org/oai"       
        self.cs_set = "cs:cs"                              
        self.arxiv_metadata_type = "arXivRaw"                              
        self.papers_xml = None
        self.papers_json = None
        self.xml_stored_revisions = None
    
    def synchronise_ai_papers(self):
        # The XML can have multiple revisions of the same paper
        self.synchronise_xml()

        # The JSON file only stores the latest revision of each paper
        self.xml_to_ai_json()
    
    def xml_to_ai_json(self):
        print(f"Converting and filtering the contents of {self.xml_data_path} to {self.json_ai_papers_path}...")
        self.load_from_xml()
        relevant_categories = [
            "cs:cs:AI",
            "cs:cs:CL",
            "cs:cs:LG",
            "cs:cs:MA"
        ]
        self.filter_by_categories(relevant_categories)
        self.save_to_json(self.json_ai_papers_path)

    def synchronise_xml(self):
        print(f"Synchronising the contents of {self.xml_data_path}...")
        newest_date, stored_revisions = self._get_current_repo_metadata()
        print(f"Currently {len(stored_revisions)} revisions in the XML file, up to {newest_date}")

        # subtract one day from from_date, to ensure we get any papers that might have been out of order
        from_date = (newest_date - timedelta(days=1)).strftime(self.date_format)
        print(f"Syncing from {from_date} to avoid missed papers")

        new_papers, updated_papers, downloaded_papers = self._sync_from_date(from_date, stored_revisions)
        print(f"{downloaded_papers} papers had already been downloaded.")
        print(f"{updated_papers} papers were updated.")
        print(f"{new_papers} new papers were downloaded.")

    def load_from_xml(self):
        self.papers_xml = self._load_papers_xml()
        print(f"Loaded {len(self.papers_xml)} papers from {self.xml_data_path}")
    
    def load_from_json(self):
        with open(self.json_ai_papers_path, "rt", encoding="utf-8") as f:
            self.papers_json = json.load(f)

        print(f"Loaded {len(self.papers_json)} papers from {self.json_ai_papers_path}")

        return self.papers_json
    
    def save_to_json(self, json_file_path):
        # 1. filter the papers loaded from XML by latest revision
        self._filter_by_latest_revision()

        print(f"Saving {len(self.papers_xml)} papers to {json_file_path}")
        assert self.papers_xml is not None, "You must load the XML file first"

        if not os.path.exists(json_file_path):
            stored_json_papers = []
        else:
            with open(json_file_path, "rt", encoding="utf-8") as f:
                stored_json_papers = json.load(f)
        
        # 2. Apply any updated revisions to the JSON papers to update stored_json_papers
        json_stored_revisions = set()
        updated_json_papers = []
        non_updated_json_papers = []
        for paper_from_json in stored_json_papers:
            id = paper_from_json["metadata"]["arXivRaw"]["id"]
            paper_date_from_json = datetime.strptime(paper_from_json["header"]["datestamp"], self.date_format)
            json_stored_revisions.add(id)

            assert id in self.xml_stored_revisions

			# From the XML file, we have the latest revision and version of each paper
            newest_paper_from_xml, newest_revision_date_from_xml = self.xml_stored_revisions[id]
            if newest_revision_date_from_xml > paper_date_from_json:
                updated_json_papers.append(newest_paper_from_xml)
            else:
                non_updated_json_papers.append(paper_from_json)

        stored_json_papers = non_updated_json_papers + updated_json_papers

        # 3. Add completely new papers to the top of the list
        new_papers = []
        for paper in self.papers_xml:
            id = paper["metadata"]["arXivRaw"]["id"]

			# Stored revisions is of the XML, rather than the JSON
            if id not in json_stored_revisions:
                new_papers.append(paper)
                json_stored_revisions.add(id)
        
        print(f"Found {len(new_papers)} new papers to add to {json_file_path}")
        print(f"Found {len(updated_json_papers)} papers to update in {json_file_path}")
        print(f"Adding {len(new_papers)} new papers to {json_file_path}")

        # 4. Combine the stored, updated json papers with the new papers and save
        stored_json_papers.extend(new_papers)
        with open(json_file_path, "wt", encoding="utf-8") as f:
            json.dump(stored_json_papers, f, indent=4)
        
        self.papers_json = stored_json_papers

    
    def filter_by_categories(self, categories):
        filtered_papers = []

        for paper in self.papers_xml:
            if any(category in paper["header"]["setSpec"] for category in categories):
                filtered_papers.append(paper)

        print(f"Filtered to {len(filtered_papers)} papers that appear in {categories}.")
        self.papers_xml = filtered_papers
    
    def _filter_by_latest_revision(self):
        stored_revisions = OrderedDict()
        paper_updates = 0
        for paper in self.papers_xml:
            id = paper["metadata"]["arXivRaw"]["id"]
            date = datetime.strptime(paper["header"]["datestamp"], self.date_format)

            if id not in stored_revisions:
                # Add new paper to the top of the list
                stored_revisions[id] = (paper, date)
            else:
                # We've already seen a revision of this paper, so we need to check if this is the latest revision
                _, stored_date = stored_revisions[id]
                if date > stored_date:
                    # This is a new revision, so we need to replace the old revision and bring to the top of the list
                    stored_revisions.pop(id)
                    stored_revisions[id] = (paper, date)
                    paper_updates += 1

        print(f"Found {paper_updates} updated revisions of papers in the XML file.")

        filtered_papers = []
        for id, (paper, _) in stored_revisions.items():
            filtered_papers.append(paper)
        
        print(f"XML file now has {len(filtered_papers)} papers, with the latest revision of each paper.")

        self.papers_xml = filtered_papers
        self.xml_stored_revisions = stored_revisions

    
    def _get_current_repo_metadata(self):
        papers = self._load_papers_xml()

        stored_revisions = {}
        newest_date = datetime.strptime("1970-01-01", self.date_format)
        for paper in papers:
            date = datetime.strptime(paper["header"]["datestamp"], self.date_format)
            if date > newest_date:
                newest_date = date
            
            id = paper["metadata"]["arXivRaw"]["id"]
            if id not in stored_revisions:
                stored_revisions[id] = date
            else:
                stored_revisions[id] = max(stored_revisions[id], date)
        
        return newest_date, stored_revisions
    
    def _sync_from_date(self, from_date, stored_revisions):
        sickle = Sickle(self.base_url)

        records = sickle.ListRecords(**{
            'metadataPrefix': self.arxiv_metadata_type,
            'set': self.cs_set,
            'ignore_deleted': True,  # skip withdrawn items
            'from': from_date
        })

        new_papers = 0
        updated_papers = 0
        downloaded_papers = 0
        with open(self.xml_data_path, "at", encoding="utf-8") as f:
            for i, new_record in enumerate(records, 1):
                assert len(new_record.metadata["id"]) == 1
                current_id = new_record.metadata["id"][0]
                revision_submission_date = datetime.strptime(new_record.header.datestamp, self.date_format)

                if current_id in stored_revisions:
                    # We've already seen a revision of this paper, so we need to check if this is the latest revision
                    stored_submission_date = stored_revisions[current_id]
                    if stored_submission_date >= revision_submission_date:
                        # We already have this revision, so we can skip it
                        downloaded_papers += 1
                    else:
                        # This is a new revision, so we need to update the latest observed revision date, and add the new revision to the XML file
                        stored_revisions[current_id] = revision_submission_date
                        f.write(new_record.raw + "\n")
                        updated_papers += 1
                else:
                    stored_revisions[current_id] = revision_submission_date
                    f.write(new_record.raw + "\n")
                    new_papers += 1
        
        return new_papers, updated_papers, downloaded_papers
    
    def _load_papers_xml(self):
        with open(self.xml_data_path, "rt", encoding="utf-8") as f:
            record_lines = f.readlines()

        record_lines.insert(0, "<records>")
        record_lines.append("</records>")
        xml_text = "".join(record_lines)
        records_dict = xmltodict.parse(xml_text)
        papers = records_dict["records"]["record"]

        return papers

if __name__ == "__main__":
    # repo = ArXivRepository("data/arxiv/test_arxiv_cs_records.xml")
    repo = ArXivRepository(
        "data/arxiv/arxiv_cs_records.xml",
        "data/arxiv/arxiv_ai_papers.json")

    # repo.synchronise_ai_papers()
    papers = repo.load_from_json()

	# 80M tokens
    total_words = 0
    for paper in papers:
        abstract = paper["metadata"]["arXivRaw"]["abstract"]
        num_words = len(abstract.split())

        total_words += num_words
    
    words_per_token = 0.75
    total_words_millions = total_words / 1000000
    total_tokens_millions = total_words / words_per_token / 1000000
    print(f"Total words: {total_words_millions:.2f} million")
    print(f"Total tokens: {total_tokens_millions:.2f} million")

