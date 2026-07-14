#!/usr/bin/env python3
"""
Test MOSS-Transcribe-Diarize 0.9B vs Whisper large-v3-turbo
on the same audio file. Outputs side-by-side comparison.

Usage: python test_moss_vs_whisper.py <audio_file.m4a>
"""
import sys
import os
import time
import json
from pathlib import Path

# Add NVIDIA DLL paths to PATH before importing faster_whisper
nvidia_base = os.path.join(os.path.dirname(os.__file__), "site-packages", "nvidia")
if os.path.exists(nvidia_base):
    dll_paths = []
    for dirpath, dirnames, filenames in os.walk(nvidia_base):
        if any(f.endswith(".dll") for f in filenames):
            dll_paths.append(dirpath)
            try:
                os.add_dll_directory(dirpath)
            except Exception:
                pass
    os.environ["PATH"] = ";".join(dll_paths) + ";" + os.environ.get("PATH", "")


def test_whisper(audio_path: str) -> dict:
    from faster_whisper import WhisperModel

    print("=" * 60)
    print("WHISPER large-v3-turbo")
    print("=" * 60)

    model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
    start = time.time()
    segments, info = model.transcribe(audio_path, language="en", beam_size=5)
    
    transcript_parts = []
    for seg in segments:
        transcript_parts.append(f"[{seg.start:.2f}-{seg.end:.2f}] {seg.text}")
    
    elapsed = time.time() - start
    full_text = "\n".join(transcript_parts)
    
    print(f"Language: {info.language} (prob: {info.language_probability:.2f})")
    print(f"Duration: {info.duration:.1f}s")
    print(f"Transcription time: {elapsed:.1f}s")
    print(f"Speed: {info.duration / elapsed:.1f}x realtime")
    print(f"Segments: {len(transcript_parts)}")
    print()
    print("TRANSCRIPT:")
    print(full_text[:3000])
    if len(full_text) > 3000:
        print(f"... ({len(full_text)} chars total)")
    
    return {
        "model": "whisper-large-v3-turbo",
        "language": info.language,
        "duration": info.duration,
        "elapsed": elapsed,
        "speed": f"{info.duration / elapsed:.1f}x",
        "segments": len(transcript_parts),
        "text": full_text,
        "text_length": len(full_text),
    }


def test_moss(audio_path: str) -> dict:
    """Transcribe with MOSS-Transcribe-Diarize 0.9B."""
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor
    from moss_transcribe_diarize import parse_transcript
    from moss_transcribe_diarize.inference_utils import (
        build_transcription_messages,
        generate_transcription,
        resolve_device,
    )

    print("=" * 60)
    print("MOSS-Transcribe-Diarize 0.9B")
    print("=" * 60)

    model_id = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
    device = resolve_device("auto")
    dtype = torch.bfloat16 if device.type == "cuda" else torch.float32

    print(f"Device: {device}, dtype: {dtype}")
    print("Loading model...")
    start_load = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True, dtype="auto"
    ).to(dtype=dtype).to(device).eval()
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    load_time = time.time() - start_load
    print(f"Model loaded in {load_time:.1f}s")

    messages = build_transcription_messages(audio_path)
    start = time.time()
    result = generate_transcription(model, processor, messages, max_new_tokens=16384)
    elapsed = time.time() - start

    # Parse the transcript
    parsed = parse_transcript(result)
    
    # Count speakers
    speakers = set()
    for seg in parsed:
        if seg.get("speaker"):
            speakers.add(seg["speaker"])
    
    # Format output
    lines = []
    for seg in parsed:
        spk = seg.get("speaker", "?")
        start_t = seg.get("start", 0)
        end_t = seg.get("end", 0)
        text = seg.get("text", "")
        lines.append(f"[{start_t:.2f}-{end_t:.2f}][{spk}] {text}")
    
    full_text = "\n".join(lines)
    
    print(f"Transcription time: {elapsed:.1f}s")
    print(f"Speakers detected: {len(speakers)} ({', '.join(sorted(speakers))})")
    print(f"Segments: {len(parsed)}")
    print()
    print("TRANSCRIPT:")
    print(full_text[:3000])
    if len(full_text) > 3000:
        print(f"... ({len(full_text)} chars total)")

    return {
        "model": "moss-0.9b",
        "elapsed": elapsed,
        "load_time": load_time,
        "speakers": len(speakers),
        "speaker_labels": sorted(list(speakers)),
        "segments": len(parsed),
        "text": full_text,
        "text_length": len(full_text),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_moss_vs_whisper.py <audio_file.m4a>")
        sys.exit(1)
    
    audio_path = sys.argv[1]
    if not Path(audio_path).exists():
        print(f"File not found: {audio_path}")
        sys.exit(1)
    
    print(f"Testing with: {audio_path}")
    print()
    
    # Run Whisper
    whisper_result = test_whisper(audio_path)
    print("\n")
    
    # Run MOSS
    moss_result = test_moss(audio_path)
    print("\n")
    
    # Comparison
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<25} {'Whisper':<20} {'MOSS':<20}")
    print("-" * 65)
    print(f"{'Model size':<25} {'809M params':<20} {'908M params':<20}")
    print(f"{'Transcription time':<25} {whisper_result['elapsed']:<20.1f} {moss_result['elapsed']:<20.1f}")
    print(f"{'Text length (chars)':<25} {whisper_result['text_length']:<20} {moss_result['text_length']:<20}")
    print(f"{'Segments':<25} {whisper_result['segments']:<20} {moss_result['segments']:<20}")
    speakers_str = f"{moss_result['speakers']} speakers)"
    print(f"{'Speaker diarization':<25} {'No':<20} {speakers_str:<20}")
    print(f"{'Speed':<25} {whisper_result['speed']:<20} {'N/A':<20}")
    
    # Save results
    output_path = Path(audio_path).stem + "_comparison.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"whisper": whisper_result, "moss": moss_result}, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")
    
    # Save transcripts side by side
    txt_path = Path(audio_path).stem + "_comparison.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("WHISPER large-v3-turbo\n")
        f.write("=" * 60 + "\n")
        f.write(whisper_result["text"] + "\n\n")
        f.write("=" * 60 + "\n")
        f.write("MOSS-Transcribe-Diarize 0.9B\n")
        f.write("=" * 60 + "\n")
        f.write(moss_result["text"] + "\n")
    print(f"Transcripts saved to: {txt_path}")


if __name__ == "__main__":
    main()
