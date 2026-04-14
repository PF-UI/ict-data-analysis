"""从 YAML 加载 Skill 定义。"""
from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import PurePosixPath

import yaml

from app.agent_runtime.skills.schema import SkillSpec


def _skill_path(name: str) -> str:
    return str(PurePosixPath(f"{name}.yaml"))


@lru_cache(maxsize=16)
def load_skill(skill_id: str) -> SkillSpec:
    raw = resources.files(__package__).joinpath(_skill_path(skill_id)).read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid skill file: {skill_id}")
    return SkillSpec.model_validate(data)
