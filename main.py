from openai import OpenAI
from dotenv import load_dotenv
import os

# Check out the models here: https://openrouter.ai/models
# https://openrouter.ai/models
# Check out my usage here: https://openrouter.ai/activity
# Models I've used
# openai/gpt-4o

def get_completion(client, prompt, model="openai/gpt-4o"):
    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]
    completion = client.chat.completions.create(
        model=model,
        messages=messages
    )
    return completion.choices[0].message.content

def main():
    load_dotenv()  # take environment variables
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    client = OpenAI(
      base_url="https://openrouter.ai/api/v1",
      api_key=openrouter_api_key,
    )

    message = get_completion(client, "What is the meaning of life?")
    
    print(message)

if __name__ == "__main__":
    main()

