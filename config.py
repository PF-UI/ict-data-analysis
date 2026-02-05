import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv() 

LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-max")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:3000/v1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

llm = ChatOpenAI(
    model=LLM_MODEL, 
    temperature=LLM_TEMPERATURE, 
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL, 
)



if __name__ == "__main__":
    print(llm.invoke("Hello, how are you?"))
