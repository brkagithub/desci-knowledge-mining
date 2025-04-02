import anthropic
import os
from dotenv import load_dotenv
import random

load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
api_key_second = os.getenv("ANTHROPIC_API_KEY_SECOND")


def select_api_key():
    return api_key if random.random() < 2 / 3 else api_key_second


def get_client():
    selected_api_key = select_api_key()
    return anthropic.Anthropic(api_key=selected_api_key)


def generate_response(client, prompt, model="claude-3-haiku-20240307", max_tokens=1500):
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.content:
        return response.content[0].text
    else:
        raise Exception("No response received from Claude.")
