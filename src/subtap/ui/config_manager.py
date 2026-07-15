"""配置文件读写管理。"""

import logging
from pathlib import Path
from typing import Any

from subtap.schemas.config import SubtapConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            import yaml

            with open(self.path, "r", encoding="utf-8") as f:
                result = yaml.safe_load(f)
                if result is None:
                    self._data = {}
                elif isinstance(result, dict):
                    self._data = result
                else:
                    raise ValueError("配置根节点必须是键值映射")
        except Exception as e:
            logger.error("Failed to load config from %s: %s", self.path, e)
            raise RuntimeError(f"配置文件读取失败：{self.path}：{e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        current = self._data
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        current = self._data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                raise ValueError(
                    f"config path '{key}' conflicts: '{part}' is {type(current[part]).__name__}, not dict"
                )
            current = current[part]
        current[parts[-1]] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import yaml

        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def to_subtap_config(self) -> SubtapConfig:
        """将 YAML 配置转换为 SubtapConfig 实例。

        直接将内部 dict 传给 SubtapConfig.model_validate，
        Pydantic 会对缺失字段使用默认值。
        """
        return SubtapConfig.model_validate(self._data)

    def sync_from_config(self, config: SubtapConfig) -> None:
        """从 SubtapConfig 实例同步配置到内部 dict 并保存。"""
        self._data = config.model_dump()
        self.save()
