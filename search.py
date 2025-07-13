import os

from dotenv import load_dotenv
from ConferenceSearchEngine import ConferenceSearchEngine

def pretty_print_doc(doc):
	title_str = ""
	title_str += doc.metadata["title"]
	title_str += f" ({','.join(doc.metadata['conference'])}"
	title_str += f" {doc.metadata['year']}"
	title_str += f", {doc.metadata['session']})"


	print(title_str)
	print(doc.metadata["authors"])
	print()
	print(doc.page_content)
	print()
	print(doc.metadata["link"])
	print()
	print()

def main():
	load_dotenv()

	# TODO: Make support many different embedding models + experiment with different embedding models. Add multiple named embeddings for each document.
	# TODO: Experiment with better ways of doing the actual similarity search, like what queries I should use.
	# TODO: Merge this repo with my conference scraper
	# TODO: Add a way of doing a pass on existing documents and appending a new kind of embedding
	# TODO: Add more conferences (MLSys, HPCA, ISCA), now I can realistically process all of this information
	# TODO: Add AI conferences (NeurIPS, ICML, ICLR, etc.)
	# TODO: Run some kind of cronjob that processes data feeds and alerts me of new relevant information, storing any information that was relevant
	# TODO: Add additional data sources (e.g. arxiv, email feeds, blogs)

	search_engine = ConferenceSearchEngine(
		embedded_docs_path="data/docs/gemini_embedded_docs.json",
		embedding_model="models/embedding-001",
		# filter=lambda metadata: int(metadata["year"]) > 2023,
		# filter=lambda metadata: "OSDI" in metadata["conference"],
		filter=lambda _: True,
		google_api_key=os.environ["GOOGLE_API_KEY"]
	)

	query = "Large language model (LLM) applications are evolving beyond simple chatbots into dynamic, general-purpose agentic programs, which scale LLM calls and output tokens to help AI agents reason, explore, and solve complex tasks. However, existing LLM serving systems ignore dependencies between programs and calls, missing significant opportunities for optimization. Our analysis reveals that programs submitted to LLM serving engines experience long cumulative wait times, primarily due to head-of-line blocking at both the individual LLM request and the program.  To address this, we introduce Autellix, an LLM serving system that treats programs as first-class citizens to minimize their end-to-end latencies."

	docs = search_engine.vs.similarity_search(query, k=10)

	for doc in docs:
		pretty_print_doc(doc)

if __name__ == "__main__":
	main()

	

	