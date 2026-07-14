"""A/B alignment comparison script.

Compares sentence-level (old) vs word-level (new) forced alignment
on real audio to verify the optimization actually improves results.

Usage:
    python scripts/compare_alignment.py --audio <file> [--output <dir>]

Requires:
    - mlx-audio installed
    - Aligner model at models/aligner/
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mlx_audio.stt.generate import generate_transcription, load_model


def _fmt_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run_baseline(model, audio_path: str, text: str) -> list[dict]:
    """Old approach: generate_transcription (sentence-level)."""
    result = generate_transcription(
        model=model, audio=audio_path, text=text, format="json"
    )
    segments = []
    if hasattr(result, "segments") and result.segments:
        for seg in result.segments:
            segments.append(
                {
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": seg.get("text", ""),
                }
            )
    return segments


def run_optimized(
    model, audio_path: str, sentences: list[str], language: str
) -> list[dict]:
    """New approach: model.generate() (word-level), one sentence at a time."""
    all_results = []
    for sent in sentences:
        if not sent.strip():
            continue
        try:
            align_result = model.generate(
                audio=audio_path, text=sent.strip(), language=language
            )
            words = []
            for item in align_result:
                words.append(
                    {
                        "word": item.text,
                        "start_sec": round(item.start_time, 3),
                        "end_sec": round(item.end_time, 3),
                    }
                )

            if words:
                all_results.append(
                    {
                        "start": words[0]["start_sec"],
                        "end": words[-1]["end_sec"],
                        "text": sent.strip(),
                        "words": words,
                    }
                )
            else:
                all_results.append(
                    {
                        "start": 0.0,
                        "end": 0.0,
                        "text": sent.strip(),
                        "words": [],
                    }
                )
        except Exception as e:
            all_results.append(
                {
                    "start": 0.0,
                    "end": 0.0,
                    "text": sent.strip(),
                    "words": [],
                    "error": str(e),
                }
            )
    return all_results


def compare(
    baseline: list[dict],
    optimized: list[dict],
) -> dict:
    """Compare baseline and optimized alignment results."""
    n = min(len(baseline), len(optimized))
    if n == 0:
        return {
            "error": "No comparable segments",
            "baseline_count": len(baseline),
            "optimized_count": len(optimized),
        }

    start_diffs = []
    end_diffs = []
    word_counts = []
    monotonic_ok = 0
    first_last_ok = 0

    for i in range(n):
        b = baseline[i]
        o = optimized[i]

        start_diffs.append(abs(o["start"] - b["start"]))
        end_diffs.append(abs(o["end"] - b["end"]))

        words = o.get("words", [])
        word_counts.append(len(words))

        if words:
            # Check word monotonicity
            ok = all(
                words[j]["start_sec"] < words[j]["end_sec"]
                and (j == 0 or words[j]["start_sec"] >= words[j - 1]["end_sec"])
                for j in range(len(words))
            )
            if ok:
                monotonic_ok += 1

            # Check first/last word == sentence boundary
            if (
                abs(words[0]["start_sec"] - o["start"]) < 0.001
                and abs(words[-1]["end_sec"] - o["end"]) < 0.001
            ):
                first_last_ok += 1

    return {
        "segment_count": n,
        "start_offset_mean_ms": round(statistics.mean(start_diffs) * 1000, 1),
        "start_offset_p50_ms": round(statistics.median(start_diffs) * 1000, 1),
        "start_offset_max_ms": round(max(start_diffs) * 1000, 1),
        "end_offset_mean_ms": round(statistics.mean(end_diffs) * 1000, 1),
        "end_offset_p50_ms": round(statistics.median(end_diffs) * 1000, 1),
        "end_offset_max_ms": round(max(end_diffs) * 1000, 1),
        "word_count_mean": round(statistics.mean(word_counts), 1) if word_counts else 0,
        "word_coverage": f"{sum(1 for w in word_counts if w > 0)}/{n}",
        "word_monotonic_ok": f"{monotonic_ok}/{sum(1 for w in word_counts if w > 0)}",
        "first_last_consistency": f"{first_last_ok}/{sum(1 for w in word_counts if w > 0)}",
    }


def generate_report(
    audio_path: str,
    language: str,
    baseline: list[dict],
    optimized: list[dict],
    stats: dict,
    elapsed_baseline: float,
    elapsed_optimized: float,
) -> str:
    """Generate markdown comparison report."""
    lines = [
        "# Alignment A/B Comparison Report",
        "",
        f"**Audio**: `{audio_path}`",
        f"**Language**: {language}",
        "",
        "## Performance",
        f"- Baseline (generate_transcription): {elapsed_baseline:.2f}s",
        f"- Optimized (model.generate): {elapsed_optimized:.2f}s",
        "",
        "## Quality Metrics",
        f"- Segment count: {stats.get('segment_count', 0)}",
        f"- Start offset mean/p50/max: {stats.get('start_offset_mean_ms', '?')}ms / {stats.get('start_offset_p50_ms', '?')}ms / {stats.get('start_offset_max_ms', '?')}ms",
        f"- End offset mean/p50/max: {stats.get('end_offset_mean_ms', '?')}ms / {stats.get('end_offset_p50_ms', '?')}ms / {stats.get('end_offset_max_ms', '?')}ms",
        f"- Word count mean: {stats.get('word_count_mean', 0)}",
        f"- Word coverage: {stats.get('word_coverage', '?')}",
        f"- Word monotonicity: {stats.get('word_monotonic_ok', '?')}",
        f"- First/last consistency: {stats.get('first_last_consistency', '?')}",
        "",
        "## Side-by-Side SRT",
        "",
        "| # | Baseline | Optimized | Offset | Words |",
        "|---|----------|-----------|--------|-------|",
    ]

    n = min(len(baseline), len(optimized), 10)
    for i in range(n):
        b = baseline[i]
        o = optimized[i]
        b_srt = f"{_fmt_srt(b['start'])} → {_fmt_srt(b['end'])}"
        o_srt = f"{_fmt_srt(o['start'])} → {_fmt_srt(o['end'])}"
        offset = round((o["start"] - b["start"]) * 1000)
        wc = len(o.get("words", []))
        lines.append(f"| {i+1} | {b_srt} | {o_srt} | {offset:+d}ms | {wc} |")

    if len(optimized) > 10:
        lines.append(f"| ... | | | | ({len(optimized) - 10} more) |")

    # Word-level sample
    lines.extend(["", "## Word-Level Sample (first 3 segments)", ""])
    for i in range(min(3, len(optimized))):
        o = optimized[i]
        words = o.get("words", [])
        lines.append(f"**Segment {i+1}**: \"{o['text']}\"")
        for j, w in enumerate(words[:8]):
            lines.append(
                f"  - Word {j+1}: \"{w['word']}\" [{w['start_sec']:.3f}s - {w['end_sec']:.3f}s]"
            )
        if len(words) > 8:
            lines.append(f"  - ... ({len(words) - 8} more words)")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="A/B alignment comparison")
    parser.add_argument("--audio", required=True, help="Audio file path")
    parser.add_argument(
        "--text",
        default=None,
        help="Text file path (one sentence per line). If omitted, uses a built-in sample.",
    )
    parser.add_argument(
        "--language",
        default="Chinese",
        help="Language (Chinese/English/Japanese/Korean)",
    )
    parser.add_argument("--output", default=None, help="Output directory for report")
    args = parser.parse_args()

    audio_path = str(Path(args.audio).resolve())

    # Load text
    if args.text:
        text_content = Path(args.text).read_text(encoding="utf-8").strip()
        sentences = [line.strip() for line in text_content.splitlines() if line.strip()]
        full_text = " ".join(sentences)
    else:
        # Use a simple sample for quick test
        sentences = ["你好世界，这是一个测试。"]
        full_text = sentences[0]
        print(f'[INFO] No --text provided, using sample: "{full_text}"')

    # Load model
    model_path = str(Path(__file__).resolve().parents[1] / "models" / "aligner")
    print(f"[INFO] Loading model from {model_path} ...")
    model = load_model(model_path)
    print(f"[INFO] Model loaded: {type(model._model).__name__}")
    print(f"[INFO] Sentences: {len(sentences)}")

    # Run baseline (generate_transcription treats full text as one block)
    print("[INFO] Running baseline (generate_transcription) ...")
    t0 = time.time()
    baseline = run_baseline(model, audio_path, full_text)
    elapsed_baseline = time.time() - t0
    print(f"[INFO] Baseline: {len(baseline)} segments in {elapsed_baseline:.2f}s")

    # Run optimized (one sentence at a time, like Subtap pipeline)
    print("[INFO] Running optimized (model.generate, per-sentence) ...")
    t0 = time.time()
    optimized = run_optimized(model, audio_path, sentences, args.language)
    elapsed_optimized = time.time() - t0
    print(f"[INFO] Optimized: {len(optimized)} segments in {elapsed_optimized:.2f}s")

    # Compare
    stats = compare(baseline, optimized)
    print("\n[RESULTS]")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Generate report
    report = generate_report(
        audio_path,
        args.language,
        baseline,
        optimized,
        stats,
        elapsed_baseline,
        elapsed_optimized,
    )

    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "comparison_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n[INFO] Report written to {report_path}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()
