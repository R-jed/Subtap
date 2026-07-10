import statistics


def calculate_metrics(sentences: list[str]) -> dict:
    """计算断句量化指标"""
    if not sentences:
        return {
            "sentence_count": 0,
            "sentence_length_mean": 0.0,
            "sentence_length_std": 0.0,
            "sentence_length_min": 0,
            "sentence_length_max": 0,
        }

    lengths = [len(s) for s in sentences]

    return {
        "sentence_count": len(sentences),
        "sentence_length_mean": statistics.mean(lengths),
        "sentence_length_std": statistics.stdev(lengths) if len(lengths) > 1 else 0.0,
        "sentence_length_min": min(lengths),
        "sentence_length_max": max(lengths),
    }
