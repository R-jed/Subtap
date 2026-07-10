"""SRT 字幕生成工具"""


def format_srt_time(seconds: float) -> str:
    """将秒数转换为 SRT 时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(sentences: list[str], timestamps: list[tuple[float, float]]) -> str:
    """生成 SRT 字幕内容"""
    if not sentences:
        return ""

    lines = []
    for i, (sentence, (start, end)) in enumerate(zip(sentences, timestamps), 1):
        lines.append(str(i))
        lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        lines.append(sentence)
        lines.append("")

    return "\n".join(lines)
