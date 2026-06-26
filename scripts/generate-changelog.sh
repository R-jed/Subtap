#!/bin/bash
# scripts/generate-changelog.sh
# 自动生成 CHANGELOG.md

set -e

echo "# Changelog" > CHANGELOG.md
echo "" >> CHANGELOG.md
echo "## v0.1.0 ($(date +%Y-%m-%d))" >> CHANGELOG.md
echo "" >> CHANGELOG.md

# 从 git log 提取 conventional commits
git log --oneline --no-merges | grep -E "(feat|fix|docs|refactor|test):" | while read -r line; do
    # 提取类型和描述（跳过 commit hash）
    # 格式：<hash> <type>: <description>
    type=$(echo "$line" | awk '{print $2}' | cut -d: -f1)
    desc=$(echo "$line" | cut -d' ' -f3- | cut -d: -f2-)

    # 根据类型添加 emoji
    case "$type" in
        feat) echo "✨$desc" >> CHANGELOG.md ;;
        fix) echo "🐛$desc" >> CHANGELOG.md ;;
        docs) echo "📚$desc" >> CHANGELOG.md ;;
        refactor) echo "♻️$desc" >> CHANGELOG.md ;;
        test) echo "✅$desc" >> CHANGELOG.md ;;
    esac
done

echo "CHANGELOG.md 已生成"
