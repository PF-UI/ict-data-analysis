"""提示词模板：按名称加载包内文本文件。"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=32)
def load_prompt_text(name: str) -> str:
    """name 不含扩展名，对应 prompts目录下 {name}.txt"""
    return resources.files(__package__).joinpath(f"{name}.txt").read_text(encoding="utf-8")
