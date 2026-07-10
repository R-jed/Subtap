#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Segmentation Benchmark ==="
echo ""

# 生成 SRT
echo "1. 生成各方案 SRT..."
uv run python generate_srt.py

echo ""
echo "=== 完成 ==="
echo "SRT 文件位于: results/srt/"
echo "请人工 review 各方案 SRT 文件"
