"""Logging system with Chinese translation layer for user-facing messages."""

from __future__ import annotations

import logging
from pathlib import Path

# Chinese translation map for user-facing log messages
_LOG_TRANSLATIONS: dict[str, str] = {
    # Pipeline stages
    "Extracting audio": "提取音频中",
    "Splitting into chunks": "音频切段中",
    "Transcribing with ASR": "语音识别中",
    "Cleaning text": "文本清洗中",
    "Segmenting sentences": "智能断句中",
    "Forced alignment": "时间轴对齐中",
    "Exporting": "字幕导出中",
    # Model
    "Loading ASR model": "加载语音识别模型",
    "Loading aligner model": "加载对齐模型",
    "ASR model loaded": "语音识别模型已加载",
    "Aligner model loaded": "对齐模型已加载",
    # Errors
    "Pipeline failed": "流程执行失败",
    "Model load error": "模型加载失败",
    "File not found": "文件未找到",
    "Chunk file not found": "音频片段文件未找到",
    "ASR failed": "语音识别失败",
    "Alignment failed": "时间轴对齐失败",
}


def translate_log(msg: str) -> str:
    """Translate English log messages to Chinese for user display.

    Only translates known messages; returns original if no match.
    """
    for en, cn in _LOG_TRANSLATIONS.items():
        if en in msg:
            return msg.replace(en, cn)
    return msg


def setup_file_logger(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Set up file-only logger (English, for debugging)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "subtap.log"

    logger = logging.getLogger("subtap.file")
    logger.setLevel(level)
    logger.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    return logger


def get_user_logger() -> logging.Logger:
    """Get logger for user-facing messages (Chinese)."""
    return logging.getLogger("subtap.user")
