import os
import json

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore


# Check out the models here: https://openrouter.ai/models
# https://openrouter.ai/models
# Check out my usage here: https://openrouter.ai/activity
# Models I've used
# openai/gpt-4o
def main():
    load_dotenv()
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = os.environ["LANGSMITH_API_KEY"]

    llm = ChatOpenAI(
        model="mistralai/mistral-7b-instruct:free",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"]
    )

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=os.environ["OPENAI_API_KEY"]
    )
    vector_store = InMemoryVectorStore(embeddings)

    osdi25_path = "data/osdi_atc25.json"
    with open(osdi25_path, "r") as f:
        osdi25 = json.load(f)
    
    papers = []
    tokens_total = 0
    for session in osdi25:
        for paper in osdi25[session]:
            tokens_total += len(paper["abstract"]) + len(paper["title"])
            papers.append(paper)
    
    print(len(papers))
    
    print(f"Total tokens: {tokens_total}")

    # response = llm.invoke("How do I say Jinnan in chinese?")
    # print(response)

    # embedding = embedding_model.embed_query("How do I say Jinnan in chinese?")
    # print(len(embedding))

    # TODO: Implement a langgraph chain
    # https://medium.com/@699580621meliga/build-your-first-langraph-chain-with-openrouter-mistral-7b-c7b47fdd4ced

if __name__ == "__main__":
    main()

