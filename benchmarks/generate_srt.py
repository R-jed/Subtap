#!/usr/bin/env python3
"""生成各方案的 SRT 文件

Pipeline 跟真实导出流程对齐：
1. local_clean_text() — 规范化数字、标点、空格等
2. segment() — 纯断句逻辑
3. strip_punct() + remove_cjk_spaces() — 输出清洗（不带标点）
"""

import sys
import time
from pathlib import Path

import yaml

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.implementations.baseline import BaselineSegmentation
from benchmarks.implementations.regroup import RegroupSegmentation
from benchmarks.implementations.conjunctions import ConjunctionSegmentation
from benchmarks.implementations.anomaly import AnomalySegmentation
from benchmarks.implementations.stable_ts import StableTsSegmentation
from benchmarks.utils.srt_generator import generate_srt
from subtap.core.clean import local_clean_text
from subtap.core.itn import chinese_to_num
from subtap.core.text_utils import strip_punct, remove_cjk_spaces


# 方案映射
IMPLEMENTATIONS = {
    "baseline": BaselineSegmentation(),
    "regroup": RegroupSegmentation(),
    "conjunctions": ConjunctionSegmentation(),
    "anomaly": AnomalySegmentation(),
    "stable_ts": StableTsSegmentation(),
}


def load_config():
    config_path = Path(__file__).parent / "benchmark_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_srt_for_text(impl, text: str, output_path: Path):
    """为文本生成 SRT

    Pipeline 对齐真实导出流程：
    1. local_clean_text() — 规范化数字、标点
    2. segment() — 纯断句
    3. strip_punct() + remove_cjk_spaces() — 输出清洗
    """
    # Step 1: 规范化输入（跟 clean stage 一致）
    cleaned_text = local_clean_text(text)

    # Step 2: 断句
    start_time = time.time()
    result = impl.segment(cleaned_text)
    elapsed = time.time() - start_time

    # Step 3: 输出清洗（跟 export stage 一致）
    # chinese_to_num → strip_punct → remove_cjk_spaces
    sentences = [
        remove_cjk_spaces(strip_punct(chinese_to_num(s)))
        for s in result.sentences
    ]

    # 生成伪时间戳（基于字符比例）
    total_chars = max(sum(len(s) for s in sentences), 1)
    timestamps = []
    cursor = 0.0
    duration = 10.0  # 假设 10 秒

    for i, sent in enumerate(sentences):
        seg_dur = duration * len(sent) / total_chars
        seg_end = duration if i == len(sentences) - 1 else cursor + seg_dur
        timestamps.append((cursor, seg_end))
        cursor = seg_end

    srt_content = generate_srt(sentences, timestamps)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(srt_content, encoding="utf-8")

    return {
        "implementation": impl.name(),
        "sentence_count": len(sentences),
        "elapsed": elapsed,
        "metadata": result.metadata,
    }


def main():
    config = load_config()
    output_dir = Path(__file__).parent / "results" / "srt"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 测试边界场景
    edge_cases_dir = Path(__file__).parent / "data" / "edge_cases"

    results = []
    for case in config["data"]["edge_cases"]:
        case_path = Path(__file__).parent / case["path"]
        if not case_path.exists():
            print(f"跳过不存在的文件: {case_path}")
            continue

        text = case_path.read_text(encoding="utf-8")
        print(f"\n处理边界场景: {case['name']}")

        for impl_id, impl in IMPLEMENTATIONS.items():
            output_path = output_dir / f"{impl_id}_{case['name']}.srt"
            result = generate_srt_for_text(impl, text, output_path)
            results.append(result)
            print(f"  {impl_id}: {result['sentence_count']} 句, {result['elapsed']:.3f}s")

    # 输出汇总
    print("\n" + "=" * 60)
    print("SRT 生成完成")
    print(f"输出目录: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
