from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SegmentationResult:
    """断句结果"""
    sentences: list[str]           # 断句后的文本列表
    metadata: dict = field(default_factory=dict)  # 方案特有的元数据


class SegmentationBenchmark(ABC):
    """断句方案基准接口"""

    @abstractmethod
    def name(self) -> str:
        """方案名称"""
        ...

    @abstractmethod
    def segment(self, text: str) -> SegmentationResult:
        """执行断句

        Args:
            text: 输入文本（可带标点或无标点）

        Returns:
            SegmentationResult
        """
        ...

    def requires_word_level(self) -> bool:
        """是否需要 word-level 时间戳"""
        return False

    def requires_model(self) -> bool:
        """是否需要加载模型"""
        return False
