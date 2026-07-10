#!/usr/bin/env python3
"""生成各方案的 SRT 文件"""

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
from benchmarks.utils.srt_generator import generate_srt


# 方案映射
IMPLEMENTATIONS = {
    "baseline": BaselineSegmentation(),
    "regroup": RegroupSegmentation(),
    "conjunctions": ConjunctionSegmentation(),
    "anomaly": AnomalySegmentation(),
}


def load_config():
    config_path = Path(__file__).parent / "benchmark_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_srt_for_text(impl, text: str, output_path: Path):
    """为文本生成 SRT"""
    start_time = time.time()
    result = impl.segment(text)
    elapsed = time.time() - start_time

    # 生成伪时间戳（基于字符比例）
    total_chars = max(sum(len(s) for s in result.sentences), 1)
    timestamps = []
    cursor = 0.0
    duration = 10.0  # 假设 10 秒

    for i, sent in enumerate(result.sentences):
        seg_dur = duration * len(sent) / total_chars
        seg_end = duration if i == len(result.sentences) - 1 else cursor + seg_dur
        timestamps.append((cursor, seg_end))
        cursor = seg_end

    srt_content = generate_srt(result.sentences, timestamps)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(srt_content, encoding="utf-8")

    return {
        "implementation": impl.name(),
        "sentence_count": len(result.sentences),
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
