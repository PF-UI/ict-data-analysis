import os

from dotenv import load_dotenv

load_dotenv()

# 延迟导入避免未安装 app 包时失败（脚本场景可仍读环境变量）
from app.agent_runtime.model_factory import get_default_chat_model

# 与历史代码兼容：main.py 图抽取等仍使用 `from config import llm`
llm = get_default_chat_model()

LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-max")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:3000/v1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

if __name__ == "__main__":
    print(llm.invoke("Hello, how are you?"))
