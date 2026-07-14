import sys
import os
import argparse
import base64
import json
import urllib.request

# Add NVIDIA DLL dirs for faster-whisper
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

DEFAULT_OUTPUT_DIR = r"C:\Users\31163\shared\Grad\Lecture Audio"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


# ── Whisper (fast, primary for single-speaker lectures) ──────────────────────

def transcribe_whisper(audio_path, output_path, model_size="large-v3-turbo"):
    from faster_whisper import WhisperModel

    print(f"[Whisper] Loading model {model_size}...")
    model = WhisperModel(model_size, device="cuda", compute_type="float16")

    print(f"[Whisper] Transcribing {audio_path}...")
    segments, info = model.transcribe(audio_path, beam_size=5, language="en")

    print(f"[Whisper] Language: {info.language} ({info.language_probability:.0%}), Duration: {info.duration:.1f}s")
    print()

    lines = []
    for segment in segments:
        line = f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}"
        print(line)
        lines.append(line)

    _save_output(lines, audio_path, output_path, header=f"Language: {info.language} ({info.language_probability:.0%})\nDuration: {info.duration:.1f}s\nEngine: Whisper {model_size}\n")
    return lines


# ── MOSS (diarization, for multi-speaker recordings) ─────────────────────────

def transcribe_moss(audio_path, output_path):
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor
    from moss_transcribe_diarize import parse_transcript
    from moss_transcribe_diarize.inference_utils import (
        build_transcription_messages,
        generate_transcription,
        resolve_device,
    )

    model_id = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
    device = resolve_device("auto")
    dtype = torch.bfloat16 if device.type == "cuda" else torch.float32

    print(f"[MOSS] Loading model (device={device}, dtype={dtype})...")
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True, dtype="auto"
    ).to(dtype=dtype, device=device).eval()

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

    print(f"[MOSS] Transcribing {audio_path}...")
    messages = build_transcription_messages(audio_path)
    result = generate_transcription(
        model, processor, messages,
        max_new_tokens=8192, do_sample=False, device=device, dtype=dtype,
    )

    segments = parse_transcript(result["text"])
    lines = []
    for seg in segments:
        line = f"[{seg.start:.2f}s -> {seg.end:.2f}s] [{seg.speaker}] {seg.text}"
        print(line)
        lines.append(line)

    _save_output(lines, audio_path, output_path, header=f"Engine: MOSS-Transcribe-Diarize\nSpeaker labels: {set(s.speaker for s in segments)}\n")
    return lines


# ── Vision OCR (GLM-OCR primary, Qwen3-VL fallback) ─────────────────────────

def ocr_image(image_path, engine="glm-ocr", prompt=None):
    """OCR a single image via Ollama. Returns extracted text."""
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    if prompt is None:
        if engine == "glm-ocr":
            prompt = "Text Recognition:"
        else:
            prompt = "Read all text in this image. Output the text exactly as written, preserving formatting, line breaks, and structure."

    payload = json.dumps({
        "model": engine,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }).encode()

    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())

    return result.get("response", "")


def ocr_pdf(pdf_path, output_path, engine="glm-ocr", fallback_engine="qwen3-vl:8b"):
    """OCR a PDF using pymupdf for digital text detection + vision model for scanned pages."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    print(f"[OCR] Processing {total_pages} pages from {pdf_path}")

    all_text = []
    for page_num in range(total_pages):
        page = doc[page_num]

        # Check if page has digital text
        text_dict = page.get_text("dict")
        text_blocks = [b for b in text_dict["blocks"] if b.get("type") == 0 and b.get("text", "").strip()]

        if text_blocks:
            # Digital text — use pymupdf
            text = page.get_text()
            print(f"  Page {page_num+1}: digital text ({len(text)} chars)")
            all_text.append(f"--- Page {page_num+1} (digital) ---\n{text}")
        else:
            # Scanned/image — use OCR
            # Check image coverage
            images = page.get_images(full=True)
            page_area = page.rect.width * page.rect.height
            is_scanned = len(images) > 0  # Has images, no text

            if is_scanned:
                # Render page to image
                pix = page.get_pixmap(dpi=200)
                img_path = os.path.join(os.environ.get("TEMP", "/tmp"), f"page_{page_num+1}.png")
                pix.save(img_path)

                print(f"  Page {page_num+1}: scanning with {engine}...")
                try:
                    text = ocr_image(img_path, engine=engine)
                except Exception as e:
                    print(f"    {engine} failed ({e}), trying {fallback_engine}...")
                    try:
                        text = ocr_image(img_path, engine=fallback_engine)
                    except Exception as e2:
                        print(f"    {fallback_engine} also failed: {e2}")
                        text = "[OCR FAILED]"

                all_text.append(f"--- Page {page_num+1} (OCR: {engine}) ---\n{text}")

                # Cleanup temp image
                try:
                    os.remove(img_path)
                except:
                    pass
            else:
                all_text.append(f"--- Page {page_num+1} (empty) ---")

    doc.close()

    full_text = "\n\n".join(all_text)

    if output_path is None:
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        output_path = os.path.join(DEFAULT_OUTPUT_DIR, f"{base}.txt")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"\nSaved to {output_path}")
    return full_text


# ── Vision backup (Qwen3-VL for hard tasks) ──────────────────────────────────

def vision_analyze(image_path, prompt="Describe what you see in this image in detail."):
    """Use Qwen3-VL for general vision tasks (not OCR-specific)."""
    return ocr_image(image_path, engine="qwen3-vl:8b", prompt=prompt)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _save_output(lines, audio_path, output_path, header=""):
    if output_path is None:
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        base = os.path.splitext(os.path.basename(audio_path))[0]
        output_path = os.path.join(DEFAULT_OUTPUT_DIR, f"{base}.txt")

    with open(output_path, "w", encoding="utf-8") as f:
        if header:
            f.write(header + "=" * 50 + "\n\n")
        f.write("\n".join(lines))
    print(f"\nSaved to {output_path}")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio or OCR documents")
    sub = parser.add_subparsers(dest="command")

    # transcribe command
    t = sub.add_parser("transcribe", help="Transcribe audio file")
    t.add_argument("audio", help="Path to audio file")
    t.add_argument("output", nargs="?", default=None, help="Output file path")
    t.add_argument("--engine", choices=["whisper", "moss"], default="whisper")
    t.add_argument("--model", default="large-v3-turbo", help="Whisper model size")

    # ocr command
    o = sub.add_parser("ocr", help="OCR a PDF or image")
    o.add_argument("input", help="Path to PDF or image file")
    o.add_argument("output", nargs="?", default=None, help="Output file path")
    o.add_argument("--engine", default="glm-ocr", help="OCR engine (glm-ocr or qwen3-vl:8b)")

    # vision command
    v = sub.add_parser("vision", help="Analyze an image with Qwen3-VL")
    v.add_argument("image", help="Path to image file")
    v.add_argument("--prompt", default="Describe what you see in this image in detail.")

    args = parser.parse_args()

    if args.command == "transcribe":
        if args.engine == "whisper":
            transcribe_whisper(args.audio, args.output, args.model)
        elif args.engine == "moss":
            transcribe_moss(args.audio, args.output)
    elif args.command == "ocr":
        if args.input.lower().endswith(".pdf"):
            ocr_pdf(args.input, args.output, engine=args.engine)
        else:
            text = ocr_image(args.input, engine=args.engine)
            print(text)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"\nSaved to {args.output}")
    elif args.command == "vision":
        text = vision_analyze(args.image, args.prompt)
        print(text)
    else:
        parser.print_help()
