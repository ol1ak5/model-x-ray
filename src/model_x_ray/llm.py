import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


def build_chat_model(model: str) -> ChatOpenAI:
    load_dotenv()
    return ChatOpenAI(
        model=model,
        base_url=os.environ["NEBIUS_BASE_URL"],
        api_key=os.environ["NEBIUS_API_KEY"],
        temperature=0,
    )
