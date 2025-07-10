import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Check out the models here: https://openrouter.ai/models
# https://openrouter.ai/models
# Check out my usage here: https://openrouter.ai/activity
# Models I've used
# openai/gpt-4o
def main():
    load_dotenv()

    llm = ChatOpenAI(
        model="mistralai/mistral-7b-instruct:free",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"]
    )

    response = llm.invoke("What is the meaning of life?")
    print(response)

    # TODO: Implement a langgraph chain
    # https://medium.com/@699580621meliga/build-your-first-langraph-chain-with-openrouter-mistral-7b-c7b47fdd4ced

if __name__ == "__main__":
    main()

