from langchain_google_genai import GoogleGenerativeAIEmbeddings
import time
import os
from dotenv import load_dotenv
from math import floor
import itertools
from utils import chunked_iterable


class EmbeddingModel:
    def __init__(self, model_name):
        load_dotenv()

        self.model_name = model_name
        self.words_per_token = 0.75 # TODO: Make this more accurate
        if model_name == "models/gemini-embedding-001":

            assert os.getenv("GOOGLE_API_KEY") is not None, "GOOGLE_API_KEY is not set in the .env file or environment variables"
            self.model = GoogleGenerativeAIEmbeddings(
                model=model_name,
                api_key=os.getenv("GOOGLE_API_KEY")
            )

            # https://cloud.google.com/vertex-ai/docs/quotas#model-region-quotas
            # NOTE: can only do 1 text per request but this handled transparently by langchain
            self.max_tokens = floor(2048 * 0.75) # max abstract is 558 tokens
            self.max_requests_per_minute = floor(100_000 * 0.75) # 75% of the max requests per minute
            # Takes around 25s to serve 1000 requests, so that's around 2000 rpm (way, way below the number that 100,000 threshold)
            # So don't worry about sleeping, just go 1000 at a time
            self.batch_size = 500

            self.inter_batch_sleep_time = 60
        else:
            raise ValueError(f"Model {model_name} not supported")
    
    def embed_documents_rate_limited(self, texts):
        if len(texts) == 0:
            return
        
        assert self.model is not None, "You must load the model first"
        assert self.model_name == "models/gemini-embedding-001", "Only gemini embeddings are supported for now"

        max_texts_tokens = max([len(text.split()) for text in texts]) / self.words_per_token
        # Use 75% of the max tokens to account for unknown words to tokens mapping
        assert max_texts_tokens <= self.max_tokens, "At least one of the texts is too long to embed"

        # loop through the texts in batches of max_texts_per_request
        for texts_chunk in chunked_iterable(texts, self.batch_size):
            human_readable_time = time.strftime("%H:%M:%S", time.localtime())
            print(f"Embedding {len(texts_chunk)} texts at {human_readable_time}.")
            time_start = time.time()
            new_embeddings = self.model.embed_documents(texts_chunk)
            time_end = time.time()
            time_diff = time_end - time_start
            print(f"Done embedding {len(texts_chunk)} texts in {time_diff:.2f} seconds.")

            for embedding in new_embeddings:
                yield embedding

if __name__ == "__main__":
    chunked_list = [chunk for chunk in chunked_iterable(range(0, 100), 3)]

    print(chunked_list)
    