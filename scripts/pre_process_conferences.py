import glob
import re
import json
import os
from langchain_core.documents import Document

conference_paths = glob.glob("data/original/*.json")

missed_documents = 0
total_documents = 0
documents_json = []
for conference_path in conference_paths:
	# load the file
	with open(conference_path, "r") as f:
		conference = json.load(f)
	
	conference_filename = conference_path.split("/")[-1]

	# Get the two digit number with a regex
	year_two_digit = re.search(r'\d{2}', conference_filename).group(0)
	year_four_digit = "20" + year_two_digit

	# Get the conference name which is all text that appears before .json, not including digits
	conference_name = re.search(r'^[^0-9.]+', conference_filename).group(0)
	if "_" in conference_name:
		conference_names_unprocessed = conference_name.split("_")
	else:
		conference_names_unprocessed = [conference_name]
	
	# Make all conference names uppercase
	conference_names = []
	for conference_name in conference_names_unprocessed:
		if conference_name == "eurosys":
			conference_names.append("EuroSys")
		else:
			conference_names.append(conference_name.upper())

	for session in conference:
		for paper in conference[session]:
			metadata = {
				"title": paper["title"],
				"authors": paper["authors"],
				"link": paper["link"],
				"session": session,
				"year": year_four_digit,
				"conference": conference_names
			}
			if paper["abstract"] is None or paper["abstract"] == "":
				print("Paper has no abstract")
				print(metadata)
				missed_documents += 1
				continue
			
			if paper["title"] is None or paper["title"] == "":
				print("Paper has no title")
				print(metadata)
				missed_documents += 1
				continue
			
			try:
				# Make sure that it constructs correctly
				doc = Document(
					page_content=paper["abstract"],
					metadata=metadata
				)
				# Then add serialisable JSON
				documents_json.append({
					"page_content": paper["abstract"],
					"metadata": metadata
				})
				total_documents += 1
			except Exception as e:
				print(e)
				print("Creating document raised an exception")
				print(metadata)
				continue

# Save the documents to a json file
with open("data/docs/documents.json", "w") as f:
	json.dump(documents_json, f)

print(f"Total documents: {total_documents}")
print(f"Missed documents: {missed_documents}")