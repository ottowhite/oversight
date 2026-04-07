from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS


class ConferenceSearchEngine:
    def __init__(
        self,
        embedded_docs_path: str,
        embedding_model: str,
        filter: Callable[[dict[str, Any]], bool],
        google_api_key: str,
    ) -> None:
        documents_json: list[dict[str, Any]] = json.load(open(embedded_docs_path))
        data_embedding_model = self.get_embeddings_model(documents_json)
        assert data_embedding_model == embedding_model
        documents_json_filtered = self.filter_documents(documents_json, filter)
        embedded_texts, metadatas = self.to_embedded_texts(documents_json_filtered)

        embeddings_kwargs: dict[str, Any] = {
            "model": embedding_model,
            "api_key": google_api_key,
        }
        self.embeddings_model = GoogleGenerativeAIEmbeddings(**embeddings_kwargs)

        self.vs = FAISS.from_embeddings(
            embedded_texts, self.embeddings_model, metadatas
        )

    def to_embedded_texts(
        self, documents_json: list[dict[str, Any]]
    ) -> tuple[list[tuple[str, list[float]]], list[dict[str, Any]]]:
        texts: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []

        for doc_json in documents_json:
            # Ensure it initalises without error
            _ = Document(
                page_content=doc_json["page_content"], metadata=doc_json["metadata"]
            )

            texts.append(doc_json["page_content"])
            embeddings.append(doc_json["embedding_metadata"]["embedding"])
            metadatas.append(doc_json["metadata"])

        embedded_texts = list(zip(texts, embeddings))

        return embedded_texts, metadatas

    def get_embeddings_model(self, documents_json: list[dict[str, Any]]) -> str | None:
        embedding_model: str | None = None
        for doc_json in documents_json:
            if embedding_model is None:
                embedding_model = doc_json["embedding_metadata"]["embedding_model"]

            assert embedding_model == doc_json["embedding_metadata"]["embedding_model"]
        return embedding_model

    def filter_documents(
        self,
        documents_json: list[dict[str, Any]],
        cond: Callable[[dict[str, Any]], bool],
    ) -> list[dict[str, Any]]:
        documents_json_filtered: list[dict[str, Any]] = []

        for doc_json in documents_json:
            if cond(doc_json["metadata"]):
                documents_json_filtered.append(doc_json)

        return documents_json_filtered
