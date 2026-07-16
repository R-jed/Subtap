#!/usr/bin/env python3
"""
Claude Code PreToolUse hook — 拦截 git commit 命令，校验 commit message 格式。
从 stdin 读取 Bash tool 的 JSON 输入，提取 -m 参数进行校验。
exit 0 = 放行，exit 1 = 拒绝
"""

import json, sys, re, os


def main():
    try:
        data = json.load(sys.stdin)
    except:
        return 0  # 无法解析则放行

    tool_input = data.get("tool_input", data)
    cmd = tool_input.get("command", "")

    # 只拦截 git commit
    if "git commit" not in cmd:
        return 0

    # 跳过 --amend（允许修改已有 commit）
    if "--amend" in cmd:
        return 0

    # 跳过 --no-verify（明确绕过 hook）
    if "--no-verify" in cmd:
        return 0

    # 提取 -m 后的消息
    msg = None
    # 匹配 -m "..." 或 -m '...' 或 -m 后面直接跟文本
    m = re.search(
        r"""(?:^|\s)-m\s+(?:"([^"]*)"|'([^']*)'|(\S.*?)(?:\s*$|\s+--))""", cmd
    )
    if m:
        msg = m.group(1) or m.group(2) or m.group(3)
    elif "-m" in cmd and '"' not in cmd and "'" not in cmd:
        # -m 后面直接跟文本（无引号）
        parts = cmd.split("-m", 1)
        if len(parts) > 1:
            msg = parts[1].strip().split(" --")[0].strip()

    if not msg:
        # 没找到 -m 参数（可能是 -F 或 editor 模式），放行
        return 0

    # --- 校验规则 ---
    errors = []

    # 跳过 merge/revert commit
    if msg.startswith(("Merge ", "Revert ")):
        return 0

    # 1. 格式：<type>: <desc> 或 <type>(<scope>): <desc>
    TYPES = r"(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|wip)"
    if not re.match(rf"^{TYPES}(\([a-zA-Z0-9._-]+\))?: .+", msg):
        errors.append(
            f"格式错误，必须为 <type>: <description> 或 <type>(<scope>): <description>"
        )
        errors.append(
            f"允许的 type: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert, wip"
        )
    else:
        # 提取 description
        desc = re.sub(rf"^{TYPES}(\([a-zA-Z0-9._-]+\))?: ", "", msg)

        # 2. description 不能为空
        if not desc:
            errors.append("description 不能为空")

        # 3. 首字母小写（专有名词除外）
        PROPER_NOUNS = [
            "Python",
            "macOS",
            "iOS",
            "Android",
            "Docker",
            "Kubernetes",
            "GitHub",
            "GitLab",
            "API",
            "CI",
            "CD",
            "TUI",
            "ASR",
            "SRT",
            "VAD",
            "GPU",
            "CPU",
            "JSON",
            "YAML",
            "TOML",
            "SQL",
            "HTTP",
            "URL",
            "PR",
            "MR",
            "README",
            "CHANGELOG",
            "LICENSE",
            "SLSA",
            "Homebrew",
            "PyPI",
            "M4",
            "ARM",
            "x86",
            "ONNX",
            "CUDA",
            "PyTorch",
            "NumPy",
            "Pandas",
            "Linux",
            "Windows",
            "Swift",
        ]
        if desc and desc[0].isupper():
            if not any(desc.startswith(pn) for pn in PROPER_NOUNS):
                errors.append(f"description 首字母应小写: '{desc[:20]}...'")

        # 4. 不以句号结尾
        if desc.endswith("."):
            errors.append("description 不应以句号结尾")

        # 5. 禁止引用其他项目
        FORBIDDEN = [
            "借鉴",
            "参照",
            "基于",
            "来自",
            "仿照",
            "模仿",
            "参考",
            "inspired by",
            "based on",
            "forked from",
            "ported from",
            "borrowed from",
        ]
        for kw in FORBIDDEN:
            if kw in msg.lower() if kw.isascii() else kw in msg:
                errors.append(f"禁止引用其他项目名称（触发词: '{kw}'）")
                break

        # 6. 长度检查
        if len(desc) > 72:
            errors.append(f"description 过长（{len(desc)} 字符，建议 ≤72）")

    if errors:
        print("", file=sys.stderr)
        print("🚫 COMMIT BLOCKED — commit message 格式错误:", file=sys.stderr)
        print("", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  当前: {msg}", file=sys.stderr)
        print("", file=sys.stderr)
        # exit 2 = Claude Code 会阻断工具调用
        sys.exit(2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
