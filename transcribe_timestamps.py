"""
Bible Audio Transcription & Verse Timestamp Alignment
=====================================================
Downloads audio from manifest, transcribes with Whisper (word-level timestamps),
aligns transcription to known verse texts, and updates manifest with accurate timestamps.

Usage: python transcribe_timestamps.py [--model small] [--device cuda] [--resume]
"""

import json
import os
import sys
import re
import time
import tempfile
import argparse
import requests

# Fix Windows console encoding for emoji/unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    # Add CUDA libraries to PATH
    try:
        import nvidia.cublas
        cuda_bin = os.path.join(nvidia.cublas.__path__[0], "bin")
        if os.path.isdir(cuda_bin):
            os.environ["PATH"] = cuda_bin + os.pathsep + os.environ.get("PATH", "")
    except ImportError:
        pass
from pathlib import Path
from faster_whisper import WhisperModel
from thefuzz import fuzz

# ─── Config ───────────────────────────────────────────────────────────────────
MANIFEST_PATH = Path(__file__).parent / "manifest.json"
PROGRESS_PATH = Path(__file__).parent / "transcribe_progress.json"
OUTPUT_PATH = Path(__file__).parent / "manifest_timestamped.json"

DOWNLOAD_TIMEOUT = 120  # seconds


# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip verse numbers, punctuation."""
    text = re.sub(r'^\d+\.\s*', '', text.strip())  # strip leading "1. "
    text = re.sub(r'[^\w\s]', '', text.lower())     # remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()         # collapse whitespace
    return text


def download_audio(url: str, dest: str) -> bool:
    """Download audio file from URL."""
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ❌ Download failed: {e}")
        return False


def transcribe_audio(model: WhisperModel, audio_path: str):
    """Transcribe audio and return list of word-level segments."""
    segments, info = model.transcribe(
        audio_path,
        language="en",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=300,
        ),
    )

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })
    return words, info


def align_verses_to_words(verses: list, words: list) -> list:
    """
    Align known verse texts to transcribed words using sliding window fuzzy matching.
    Returns list of {verse, start, end, text} timestamps.

    Strategy:
    - For each verse, find the best matching window of words
    - Use fuzzy ratio to score alignment
    - Enforce monotonic ordering (each verse starts after previous)
    """
    if not words or not verses:
        return []

    timestamps = []
    search_start_idx = 0  # word index to start searching from

    for v_idx, verse_text in enumerate(verses):
        verse_num = v_idx + 1
        clean_verse = clean_text(verse_text)
        verse_word_count = len(clean_verse.split())

        if verse_word_count == 0:
            continue

        best_score = 0
        # Clamp to valid range
        clamped_start = min(search_start_idx, len(words) - 1)
        best_start_word = clamped_start
        best_end_word = min(clamped_start + 1, len(words) - 1)

        # Search window: try different starting positions
        # Look ahead but not too far (max ~3x the verse length in words)
        max_search = min(len(words), clamped_start + verse_word_count * 8)

        for start_w in range(clamped_start, max_search):
            # Try window sizes around the expected verse word count
            for window_extra in range(-max(3, verse_word_count // 3), max(5, verse_word_count // 2)):
                window_size = verse_word_count + window_extra
                if window_size < 1:
                    continue
                end_w = start_w + window_size
                if end_w > len(words):
                    break

                candidate = " ".join(w["word"] for w in words[start_w:end_w])
                candidate_clean = re.sub(r'[^\w\s]', '', candidate.lower()).strip()
                candidate_clean = re.sub(r'\s+', ' ', candidate_clean)

                score = fuzz.ratio(clean_verse, candidate_clean)

                if score > best_score:
                    best_score = score
                    best_start_word = start_w
                    best_end_word = end_w - 1

                # Perfect or near-perfect match, stop early
                if score >= 95:
                    break

            if best_score >= 95:
                break

        # Get timestamps from best matching word range
        start_time = words[best_start_word]["start"]
        end_time = words[min(best_end_word, len(words) - 1)]["end"]

        timestamps.append({
            "verse": verse_num,
            "start": round(start_time, 2),
            "end": round(end_time, 2),
            "text": verse_text,
            "confidence": best_score,
        })

        # Move search start past the matched region for next verse
        search_start_idx = best_end_word + 1

        # If confidence is low, don't advance as far (might have misaligned)
        if best_score < 50:
            search_start_idx = max(search_start_idx - verse_word_count, best_start_word + 1)

    # Post-process: fill gaps and fix overlaps
    timestamps = fix_timestamp_gaps(timestamps)

    return timestamps


def fix_timestamp_gaps(timestamps: list) -> list:
    """Ensure timestamps are monotonic and fill small gaps."""
    if len(timestamps) < 2:
        return timestamps

    for i in range(1, len(timestamps)):
        # Fix overlaps: if this verse starts before previous ends, adjust
        if timestamps[i]["start"] < timestamps[i - 1]["end"]:
            mid = (timestamps[i]["start"] + timestamps[i - 1]["end"]) / 2
            timestamps[i - 1]["end"] = round(mid, 2)
            timestamps[i]["start"] = round(mid, 2)

        # Fill small gaps: if gap between verses, extend previous end
        gap = timestamps[i]["start"] - timestamps[i - 1]["end"]
        if 0 < gap < 2.0:
            timestamps[i - 1]["end"] = timestamps[i]["start"]

    return timestamps


def load_progress() -> dict:
    """Load progress tracking file."""
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, 'r') as f:
            return json.load(f)
    return {"completed": []}


def save_progress(progress: dict):
    """Save progress tracking file."""
    with open(PROGRESS_PATH, 'w') as f:
        json.dump(progress, f, indent=2)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Transcribe Bible audio and align verse timestamps")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper model size (default: small)")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"],
                        help="Device to run on (default: cuda)")
    parser.add_argument("--compute-type", default="float16",
                        help="Compute type (default: float16 for cuda, int8 for cpu)")
    parser.add_argument("--start-from", type=int, default=0,
                        help="Start from this manifest index")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only N entries (0 = all)")
    parser.add_argument("--force", action="store_true",
                        help="Re-transcribe even if already done")
    args = parser.parse_args()

    # Auto-adjust compute type for CPU
    if args.device == "cpu" and args.compute_type == "float16":
        args.compute_type = "int8"

    # Load manifest — prefer output file if it exists (preserves already-transcribed work)
    if OUTPUT_PATH.exists():
        print(f"📖 Resuming from {OUTPUT_PATH}")
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    else:
        print(f"📖 Loading manifest from {MANIFEST_PATH}")
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    print(f"   Found {len(manifest)} chapters")

    # Load progress
    progress = load_progress()
    completed_list = progress["completed"]  # ordered list
    completed_keys = set(completed_list)    # fast lookup set
    print(f"   Already completed: {len(completed_keys)} chapters")

    # Load Whisper model
    print(f"\n🔊 Loading Whisper model '{args.model}' on {args.device} ({args.compute_type})...")
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    print("   Model loaded!\n")

    # Process entries
    start_idx = args.start_from
    end_idx = len(manifest) if args.limit == 0 else min(start_idx + args.limit, len(manifest))

    total_to_process = 0
    for i in range(start_idx, end_idx):
        entry = manifest[i]
        key = f"{entry['book']}_{entry['chapter']}"
        if key not in completed_keys or args.force:
            total_to_process += 1

    print(f"📋 Processing {total_to_process} chapters (index {start_idx} to {end_idx - 1})\n")
    processed = 0

    for i in range(start_idx, end_idx):
        entry = manifest[i]
        key = f"{entry['book']}_{entry['chapter']}"

        # Skip if already done
        if key in completed_keys and not args.force:
            continue

        processed += 1
        book = entry["book"]
        chapter = entry["chapter"]
        url = entry["url"]
        verses = entry.get("verses", [])

        print(f"[{processed}/{total_to_process}] {book} {chapter} ({len(verses)} verses)")

        if not verses:
            print("    ⚠️  No verse texts, skipping")
            continue

        if not url:
            print("    ⚠️  No audio URL, skipping")
            continue

        # Download audio to temp file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            print(f"    ⬇️  Downloading audio...")
            if not download_audio(url, tmp_path):
                continue

            file_size = os.path.getsize(tmp_path)
            print(f"    📁 Downloaded ({file_size / 1024:.0f} KB)")

            # Transcribe
            print(f"    🎙️  Transcribing...")
            t0 = time.time()
            words, info = transcribe_audio(model, tmp_path)
            elapsed = time.time() - t0
            print(f"    ✅ Transcribed {len(words)} words in {elapsed:.1f}s (audio: {info.duration:.1f}s)")

            if not words:
                print("    ⚠️  No words detected, skipping")
                continue

            # Align verses
            print(f"    🔗 Aligning {len(verses)} verses to {len(words)} words...")
            timestamps = align_verses_to_words(verses, words)

            # Report confidence
            if timestamps:
                avg_conf = sum(t["confidence"] for t in timestamps) / len(timestamps)
                low_conf = [t for t in timestamps if t["confidence"] < 60]
                print(f"    📊 Avg confidence: {avg_conf:.0f}%", end="")
                if low_conf:
                    print(f" ({len(low_conf)} low-confidence verses)", end="")
                print()

                # Strip confidence from final output (it's just for debugging)
                for t in timestamps:
                    del t["confidence"]

            # Update manifest entry
            manifest[i]["timestamps"] = timestamps

            # Mark as completed and save progress
            completed_keys.add(key)
            completed_list.append(key)
            progress["completed"] = completed_list
            save_progress(progress)

            # Save manifest periodically (every 5 chapters)
            if processed % 5 == 0:
                with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=4, ensure_ascii=False)
                print(f"    💾 Saved progress to {OUTPUT_PATH.name}")

        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

        print()

    # Final save
    print(f"\n💾 Saving final manifest to {OUTPUT_PATH}")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)

    print(f"\n✅ Done! Processed {processed} chapters.")
    print(f"   Output: {OUTPUT_PATH}")
    print(f"\nTo apply: copy {OUTPUT_PATH.name} over manifest.json and upload to R2")


if __name__ == "__main__":
    main()
