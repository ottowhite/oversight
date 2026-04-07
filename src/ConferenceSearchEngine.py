import os
import json

from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS


class ConferenceSearchEngine:
	def __init__(self, embedded_docs_path, embedding_model, filter, google_api_key):
		documents_json = json.load(open(embedded_docs_path))
		data_embedding_model = self.get_embeddings_model(documents_json)
		assert data_embedding_model == embedding_model
		documents_json_filtered = self.filter_documents(documents_json, filter)
		embedded_texts, metadatas = self.to_embedded_texts(documents_json_filtered)

		self.embeddings_model = GoogleGenerativeAIEmbeddings(
			model=embedding_model,
			api_key=google_api_key
		)

		self.vs = FAISS.from_embeddings(embedded_texts, self.embeddings_model, metadatas)

	def to_embedded_texts(self, documents_json):
		texts = []
		embeddings = []
		metadatas = []
	
		for doc_json in documents_json:
			# Ensure it initalises without error
			_ = Document(
				page_content=doc_json["page_content"],
				metadata=doc_json["metadata"]
			)
	
			texts.append(doc_json["page_content"])
			embeddings.append(doc_json["embedding_metadata"]["embedding"])
			metadatas.append(doc_json["metadata"])
	
		embedded_texts = list(zip(texts, embeddings))
	
		return embedded_texts, metadatas
	
	def get_embeddings_model(self, documents_json):
		embedding_model = None
		for doc_json in documents_json:
			if embedding_model is None:
				embedding_model = doc_json["embedding_metadata"]["embedding_model"]
			
			assert embedding_model == doc_json["embedding_metadata"]["embedding_model"]
		return embedding_model
	
	def filter_documents(self, documents_json, cond):
		documents_json_filtered = []
	
		for doc_json in documents_json:
			if cond(doc_json["metadata"]):
				documents_json_filtered.append(doc_json)
	
		return documents_json_filtered