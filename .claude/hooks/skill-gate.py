#!/usr/bin/env python3
"""Skill gate v5: GUIDANCE mode — reminds AI to scan mattpocock + plugin skills on new tasks.

Architecture:
  UserPromptSubmit → If no Skill call in recent turns, remind to scan both skill sets.
  PostToolUse(Skill) → Records that Skill was called; resets reminder counter.
  PreToolUse(*) → Light nudge only when consecutive non-Skill calls grow high.
"""

import json, os, sys

STATE_FILE = os.path.expanduser("~/.claude/.skill-gate-state.json")

# On UserPromptSubmit: remind if more than this many turns since last Skill call
USER_PROMPT_COOLDOWN = 3

# On PreToolUse: gentle nudge only after this many consecutive non-Skill tool calls
PRE_TOOL_NUDGE = 50

SKIP_TOOLS = {
    "Skill",
    "TodoWrite",
    "TaskCreate",
    "TaskUpdate",
    "EnterPlanMode",
    "ExitPlanMode",
    "Workflow",
}


def get_installed_skills():
    """动态读取已安装的 skills — mattpocock/skills + 插件 skills"""
    mattpocock = []
    plugins = []

    # 1. mattpocock/skills (symlinks in ~/.claude/skills/)
    skills_dir = os.path.expanduser("~/.claude/skills/")
    try:
        if os.path.isdir(skills_dir):
            mattpocock = sorted(
                [
                    d
                    for d in os.listdir(skills_dir)
                    if os.path.isdir(os.path.join(skills_dir, d))
                    and not d.startswith(".")
                ]
            )
    except Exception:
        pass

    # 2. 插件 skills (marketplaces)
    marketplaces_dir = os.path.expanduser("~/.claude/plugins/marketplaces/")
    try:
        if os.path.isdir(marketplaces_dir):
            for marketplace in sorted(os.listdir(marketplaces_dir)):
                m_path = os.path.join(marketplaces_dir, marketplace, "skills")
                if os.path.isdir(m_path):
                    for skill in sorted(os.listdir(m_path)):
                        s_path = os.path.join(m_path, skill)
                        if os.path.isdir(s_path) and not skill.startswith("."):
                            plugins.append(f"{skill} ({marketplace})")
    except Exception:
        pass

    result = []
    if mattpocock:
        result.append("【mattpocock Skills】\n" + ", ".join(mattpocock))
    if plugins:
        result.append("【插件 Skills】\n" + ", ".join(plugins))
    return "\n\n".join(result) if result else "(未找到已安装的 skills)"


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"turn": 0, "skill_turn": -1, "consecutive_no_skill": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def detect_event(data):
    if "session_id" in data and "cwd" in data and "tool_input" not in data:
        return "UserPromptSubmit"
    if "tool_name" in data and "tool_output" in data:
        return "PostToolUse"
    if "tool_name" in data and "tool_input" in data and "tool_output" not in data:
        return "PreToolUse"
    return ""


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    event = detect_event(data)
    state = load_state()

    if event == "UserPromptSubmit":
        turn = state.get("turn", 0) + 1
        state["turn"] = turn
        last_skill = state.get("skill_turn", -1)
        # Remind if no Skill call in recent turns
        if turn - last_skill > USER_PROMPT_COOLDOWN:
            installed = get_installed_skills()
            msg = (
                "📋 SKILL CHECK: 收到新任务。请遍历以下已安装的 skill 集，"
                "检查是否有匹配当前任务的 skill，然后调用 Skill 工具加载。\n\n"
                f"{installed}\n\n"
                "不确定用哪个 skill 时，先调用 ask-matt 路由。"
            )
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": msg,
                        }
                    }
                )
            )
        save_state(state)
        return

    if event == "PostToolUse":
        if data.get("tool_name") == "Skill":
            state["skill_turn"] = state.get("turn", 0)
            state["consecutive_no_skill"] = 0
            save_state(state)
        return

    if event == "PreToolUse":
        tool = data.get("tool_name", "")
        if tool in SKIP_TOOLS:
            return
        cns = state.get("consecutive_no_skill", 0) + 1
        state["consecutive_no_skill"] = cns
        save_state(state)
        if cns >= PRE_TOOL_NUDGE:
            installed = get_installed_skills()
            msg = (
                f"💡 SKILL REMINDER: 已连续 {cns} 次工具调用未检查 skill。"
                "如有新任务需要处理，请先调用 ask-matt 确定正确的 skill 流程。\n\n"
                f"{installed}"
            )
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": msg,
                        }
                    }
                )
            )
        return


if __name__ == "__main__":
    main()
