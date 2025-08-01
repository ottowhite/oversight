import openreview 
from pathlib import Path
import json

class OpenReviewHarvester:
    def __init__(self, name, year, output_path):
        self.output_path = Path(output_path)
        self.venue_id = {
            "icml": f"ICML.cc/{year}/Conference",
            "iclr":   f"ICLR.cc/{year}/Conference",
            "neurips": f"NeurIPS.cc/{year}/Conference",
            "mlsys":  f"MLSys.org/{year}/Conference",
        }[name]
        self.name = name
        self.year = year

        # Initial version to try with
        self.version = 2
    
    def harvest(self):
        notes = self.get_notes()
        self.save_conference(notes)
    
    def get_notes(self):
        notes = self._get_notes_versioned(2)
        if len(notes) == 0:
            # Fall back to the version 1 client
            self.version = 1
            notes = self._get_notes_versioned(1)

        return [note.to_json() for note in notes]

    def _get_notes_versioned(self, version):
        if version == 2:
            invitation = self.venue_id + "/-/Submission"
            client = openreview.api.OpenReviewClient(baseurl="https://api2.openreview.net")
            return client.get_all_notes(invitation=invitation, content={'venueid': self.venue_id})
        elif version == 1:
            invitation = self.venue_id + "/-/Blind_Submission"
            client = openreview.Client(baseurl="https://api.openreview.net")
            notes = client.get_all_notes(invitation=invitation, details="directReplies,original")
            accepted_notes = []
            accept_messages = set()
            reject_messages = set()
            for note in notes:
                decisions = [reply for reply in note.details["directReplies"] if reply["invitation"].endswith("Decision")]
                decision_str = decisions[-1]["content"]["decision"]
                is_accept = openreview.tools.is_accept_decision(decision_str)
                if is_accept:
                    accepted_notes.append(note)
                    accept_messages.add(decision_str)
                else:
                    reject_messages.add(decision_str)
            
            print("Complex accept/reject handling for OpenReview v1 client --- ")
            print(f"Found {len(accepted_notes)} accepted notes out of {len(notes)} total notes for {self.name} ({self.year})")
            print(f"Accept messages: {accept_messages}")
            print(f"Reject messages: {reject_messages}")

            return accepted_notes
    
    def save_conference(self, notes):
        if len(notes) == 0:
            print(f"No notes found for {self.name} ({self.year})")
            return
        else:
            print(f"Harvested {len(notes)} notes for {self.name} ({self.year})")
            path = self.output_path / f"{self.name}{self.year}_v{self.version}.json"
            print(f"Saving to {path}")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    conferences = [
        "icml",
        "neurips",
        "mlsys",
        "iclr"
    ]
    years = [2025, 2024, 2023, 2022, 2021, 2020]

    for conference in conferences:
        for year in years:
            harvester = OpenReviewHarvester(conference, year, "data/ai_conferences/")
            harvester.harvest()
