import time
import requests
import re
import xml.etree.ElementTree as ET
import json
from tqdm import tqdm

class ArxivCollector:
	def __init__(self):
		self.time_between_requests = 120
		self.time_of_last_request = time.time() - self.time_between_requests
		self.api_url = "http://export.arxiv.org/api/query?"
	
	def make_query(self, query):
		url = f"{self.api_url}{query}"

		time_since_last_request = time.time() - self.time_of_last_request
		seconds_until_next_request = int(self.time_between_requests - time_since_last_request)
		for _ in tqdm(range(seconds_until_next_request), desc="Waiting for next request"):
			time.sleep(1)

		# Make the request
		response = requests.get(url)
		if response.status_code != 200:
			print(f"Error: {response.status_code}")
			print(f"Response: {response.text}")
			exit(-1)
		data_xml_raw = response.text
		
		self.time_of_last_request = int(time.time())

		# Parse it to a dictionary
		data = self.xml_raw_to_dict(data_xml_raw)

		if len(data) == 0:
			print("No results found")
			print(f"returned data: {data_xml_raw}")

		return data

	@classmethod
	def xml_raw_to_dict(self, xml_raw):
		tree = ET.fromstring(xml_raw)

		# Define namespaces (must match those in the document)
		ns = {
		    'atom': 'http://www.w3.org/2005/Atom',
		    'opensearch': 'http://a9.com/-/spec/opensearch/1.1/',
		    'arxiv': 'http://arxiv.org/schemas/atom',
		}

		# Extract general metadata
		total_results = tree.find('opensearch:totalResults', ns).text
		title = tree.find('atom:title', ns).text

		print(f"Total results: {total_results}")
		print()

		entry_data = []
		entries = tree.findall('atom:entry', ns)


		for entry in entries:
			link = self.maybe_find(entry, 'atom:id', ns)
			# If there is no version number at the end of the link, use the link as the id
			if not re.search(r'v\d+', link):
				print(f"No version number in link, using link as id: {link}")
				id = link
			else:
				id = re.sub(r'v\d+', '', link)

			entry_data.append({
				'id': id,
			    'title': self.maybe_find(entry, 'atom:title', ns).replace("\n ", ""),
			    'abstract': self.maybe_find(entry, 'atom:summary', ns).replace("\n", " "),
			    'link': link,
			    'published': self.maybe_find(entry, 'atom:published', ns),
				'updated': self.maybe_find(entry, 'atom:updated', ns),
			    'doi': self.maybe_find(entry, 'arxiv:doi', ns),
				'categories': [
					category.get('term')
					for category in entry.findall('atom:category', ns)
				],
			    'authors': [
			        self.maybe_find(author, 'atom:name', ns)
			        for author in entry.findall('atom:author', ns)
			    ],
			})

		return entry_data
	
	@classmethod
	def maybe_find(self, entry, tag, ns):
		element = entry.find(tag, ns)
		if element is not None:
			# Replace newlines with spaces
			return element.text
		else:
			return None

class ArxivQueryBuilder:
	
	@staticmethod
	def build(
			overall_search=None,
			category=None,
			categories=None,
			max_results=1,
			start=0,
			sort_by="lastUpdatedDate",
			sort_order="descending"):

		predicates = []

		if overall_search is not None:
			predicates.append(f"all:{overall_search}")

		if categories is not None:
			assert category is None, "Cannot specify both category and categories"
			category_sub_queries = list(map(lambda x: f"cat:{x}", categories))
			category_full_query = "+OR+".join(category_sub_queries)
			predicates.append(category_full_query)

		if category is not None:
			assert categories is None, "Cannot specify both category and categories"
			predicates.append(f"cat:{category}")

		predicates.append(f"start={start}")
		predicates.append(f"max_results={max_results}")
		predicates.append(f"sortBy={sort_by}")
		predicates.append(f"sortOrder={sort_order}")
		query = f"search_query={'&'.join(predicates)}"
		return query
	
arxiv_collector = ArxivCollector()

# ti	Title
# au	Author
# abs	Abstract
# co	Comment
# jr	Journal Reference
# cat	Subject Category (https://arxiv.org/category_taxonomy)
# rn	Report Number
# id	Id (use id_list instead)
# all	All of the above

relevant_categories = [
# 	"cs.AI", # Artificial Intelligence ALREADY DONE
	"cs.CL", # Computation and Language
	"cs.LG", # Machine Learning
	"cs.MA", # Multi-agent systems
	"stat.ML"] # Machine Learning (Stats)


for category in relevant_categories:
	results = []

	start = 0
	results_per_query = 1000
	while True:

		query = ArxivQueryBuilder.build(category=category, max_results=results_per_query, start=start)
		new_results = arxiv_collector.make_query(query)
		results.extend(new_results)
		print(f"{len(results)} results so far for {category}")

		# Write intermediate results to the file
		with open(f"arxiv_results_{category}.json", "w") as f:
			json.dump(results, f, indent=4)

		if len(new_results) < results_per_query:
			break

		start += results_per_query


# TODO: Make this work for larger queries with the Open Archives Initiative
# TODO: Cache absolutely everything returned, so we don't have to anticipate what we're going to need again and store that.
# TODO: Store the results in a database that we can keep adding to and querying
# TODO: Integrate this data with the vector database 
# TODO: Add a functionality to add updated results to the database
# TODO: Potentially just get absolutely all the data
# TODO: Look into the open archives initiative
# 	https://www.openarchives.org/
# 	https://info.arxiv.org/help/oa/index.html