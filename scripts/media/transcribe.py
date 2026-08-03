import sys as _sys
from pathlib import Path as _Path
_sys_root = _Path(__file__).resolve().parents[2]
if str(_sys_root) not in _sys.path:
    _sys.path.insert(0, str(_sys_root))

import os
import argparse
import base64
import tempfile
import urllib.request

from scripts.core.common_client import JsonHttpClient
from scripts.core.model_availability import ensure_ollama_available

_OLLAMA_CLIENT = JsonHttpClient(
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({})),
    timeout=120,
    retries=2,
)

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

DEFAULT_OUTPUT_DIR = os.environ.get(
    "CORNELL_KB_OUTPUT_DIR",
    str(_sys_root / "data" / "artifacts" / "media"),
)
OLLAMA_URL = os.environ.get(
    "CORNELL_KB_OLLAMA_URL", "http://127.0.0.1:11434/api/generate"
)
_MODEL_CACHE = {}


def clear_model_cache():
    """Release cached model references; useful for callers and offline tests."""
    _MODEL_CACHE.clear()


def _load_whisper_model(model_size, device, compute_type):
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _whisper_cache_key(model_size, device, compute_type, model_loader):
    return ("whisper", model_size, device, compute_type, id(model_loader))


def ensure_whisper_available(
    model_size="large-v3-turbo", device="cuda", compute_type="float16",
    *, model_loader=None, reuse_model=True,
):
    """Load Whisper on demand and return a reusable runtime handle.

    Whisper is not a background service. Loading the model here is the
    on-demand equivalent of starting it; no process or OS auto-start is added.
    """
    model_loader = model_loader or _load_whisper_model
    cache_key = _whisper_cache_key(model_size, device, compute_type, model_loader)
    model = _MODEL_CACHE.get(cache_key) if reuse_model else None
    if model is not None:
        return {
            "available": True, "started": False, "model": model,
            "model_size": model_size, "device": device, "compute_type": compute_type,
        }

    try:
        model = model_loader(model_size, device, compute_type)
    except Exception as exc:
        raise RuntimeError(
            f"Whisper model {model_size!r} is unavailable on {device}/{compute_type}: {exc}"
        ) from exc
    if reuse_model:
        _MODEL_CACHE[cache_key] = model
    return {
        "available": True, "started": True, "model": model,
        "model_size": model_size, "device": device, "compute_type": compute_type,
    }


# ── Whisper (fast, primary for single-speaker lectures) ──────────────────────

def transcribe_whisper(
    audio_path, output_path, model_size="large-v3-turbo", *,
    device=None, compute_type=None, model_loader=None, reuse_model=True,
):
    """Transcribe audio with a configurable, process-reusable Whisper model."""
    device = device or os.environ.get("CORNELL_KB_WHISPER_DEVICE", "cuda")
    compute_type = compute_type or os.environ.get("CORNELL_KB_WHISPER_COMPUTE_TYPE", "float16")
    readiness = ensure_whisper_available(
        model_size, device, compute_type,
        model_loader=model_loader, reuse_model=reuse_model,
    )
    model = readiness["model"]
    if readiness["started"]:
        print(f"[Whisper] Loading model {model_size} (device={device}, compute_type={compute_type})...")
    else:
        print(f"[Whisper] Reusing model {model_size} (device={device}, compute_type={compute_type})...")

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

DEFAULT_MOSS_MODEL = "OpenMOSS-Team/MOSS-Transcribe-Diarize"


def _load_moss_runtime(model_id, device_preference):
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor
    from moss_transcribe_diarize import parse_transcript
    from moss_transcribe_diarize.inference_utils import (
        build_transcription_messages,
        generate_transcription,
        resolve_device,
    )

    device = resolve_device(device_preference)
    dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True, dtype="auto"
    ).to(dtype=dtype, device=device).eval()
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    return model, processor, device, dtype, parse_transcript, build_transcription_messages, generate_transcription


def transcribe_moss(
    audio_path, output_path, *, model_id=None, device_preference=None,
    model_loader=None, reuse_model=True,
):
    """Transcribe multi-speaker audio with a process-reusable MOSS runtime."""
    model_id = model_id or os.environ.get("CORNELL_KB_MOSS_MODEL", DEFAULT_MOSS_MODEL)
    device_preference = device_preference or os.environ.get("CORNELL_KB_MOSS_DEVICE", "auto")
    model_loader = model_loader or _load_moss_runtime
    cache_key = ("moss", model_id, device_preference, id(model_loader))
    runtime = _MODEL_CACHE.get(cache_key) if reuse_model else None
    if runtime is None:
        print(f"[MOSS] Loading model {model_id} (device={device_preference})...")
        runtime = model_loader(model_id, device_preference)
        if reuse_model:
            _MODEL_CACHE[cache_key] = runtime
    else:
        print(f"[MOSS] Reusing model {model_id} (device={device_preference})...")

    model, processor, device, dtype, parse_transcript, build_transcription_messages, generate_transcription = runtime

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

def _ollama_transport(payload, ollama_url, timeout):
    return _OLLAMA_CLIENT.post_json(ollama_url, payload, timeout=timeout)


def ocr_image(image_path, engine="glm-ocr", prompt=None, ollama_url=OLLAMA_URL, transport=None):
    """OCR one image via an injectable Ollama transport. Returns extracted text."""
    if transport is None:
        ensure_ollama_available(ollama_url, model=engine)
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    if prompt is None:
        if engine == "glm-ocr":
            prompt = "Text Recognition:"
        else:
            prompt = "Read all text in this image. Output the text exactly as written, preserving formatting, line breaks, and structure."

    payload = {
        "model": engine,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }
    result = (transport or _ollama_transport)(payload, ollama_url, 120)

    return result.get("response", "")


def ocr_pdf(
    pdf_path, output_path, engine="glm-ocr", fallback_engine="qwen3-vl:8b", *,
    ocr_func=None, render_dpi=150, temp_root=None, ollama_url=OLLAMA_URL, transport=None,
):
    """OCR a PDF, rendering scans at 150 DPI in a run-specific temp directory."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    print(f"[OCR] Processing {total_pages} pages from {pdf_path}")

    all_text = []
    ocr_func = ocr_func or ocr_image
    try:
        with tempfile.TemporaryDirectory(prefix="cornell_kb_ocr_", dir=temp_root) as temp_dir:
            for page_num in range(total_pages):
                page = doc[page_num]

                # Check if page has digital text
                text_dict = page.get_text("dict")
                text_blocks = [b for b in text_dict["blocks"] if b.get("type") == 0 and b.get("text", "").strip()]

                if text_blocks:
                    text = page.get_text()
                    print(f"  Page {page_num+1}: digital text ({len(text)} chars)")
                    all_text.append(f"--- Page {page_num+1} (digital) ---\n{text}")
                    continue

                images = page.get_images(full=True)
                if images:
                    img_path = os.path.join(temp_dir, f"page_{page_num+1}.png")
                    page.get_pixmap(dpi=render_dpi).save(img_path)

                    print(f"  Page {page_num+1}: scanning with {engine} at {render_dpi} DPI...")
                    used_engine = engine
                    try:
                        text = ocr_func(img_path, engine=engine, ollama_url=ollama_url, transport=transport)
                    except Exception as e:
                        print(f"    {engine} failed ({e}), trying {fallback_engine}...")
                        used_engine = fallback_engine
                        try:
                            text = ocr_func(img_path, engine=fallback_engine, ollama_url=ollama_url, transport=transport)
                        except Exception as e2:
                            print(f"    {fallback_engine} also failed: {e2}")
                            text = "[OCR FAILED]"
                    all_text.append(f"--- Page {page_num+1} (OCR: {used_engine}) ---\n{text}")
                else:
                    all_text.append(f"--- Page {page_num+1} (empty) ---")
    finally:
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

def vision_analyze(image_path, prompt="Describe what you see in this image in detail.", ollama_url=OLLAMA_URL, transport=None):
    """Use Qwen3-VL for general vision tasks (not OCR-specific)."""
    return ocr_image(image_path, engine="qwen3-vl:8b", prompt=prompt, ollama_url=ollama_url, transport=transport)


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

def build_parser():
    """Build the stable CLI parser so callers can inspect/configure it offline."""
    parser = argparse.ArgumentParser(description="Transcribe audio or OCR documents")
    sub = parser.add_subparsers(dest="command")

    # transcribe command
    t = sub.add_parser("transcribe", help="Transcribe audio file")
    t.add_argument("audio", help="Path to audio file")
    t.add_argument("output", nargs="?", default=None, help="Output file path")
    t.add_argument("--engine", choices=["whisper", "moss"], default="whisper")
    t.add_argument("--model", default="large-v3-turbo", help="Whisper model size")
    t.add_argument("--device", default=None, help="Whisper device (default: CORNELL_KB_WHISPER_DEVICE or cuda)")
    t.add_argument("--compute-type", default=None, help="Whisper compute type (default: CORNELL_KB_WHISPER_COMPUTE_TYPE or float16)")
    t.add_argument("--no-model-cache", dest="reuse_model", action="store_false", default=True, help="Load a fresh model for this run")
    t.add_argument("--moss-model", default=None, help="MOSS model id (default: CORNELL_KB_MOSS_MODEL)")
    t.add_argument("--moss-device", default=None, help="MOSS device preference (default: CORNELL_KB_MOSS_DEVICE or auto)")

    # ocr command
    o = sub.add_parser("ocr", help="OCR a PDF or image")
    o.add_argument("input", help="Path to PDF or image file")
    o.add_argument("output", nargs="?", default=None, help="Output file path")
    o.add_argument("--engine", default="glm-ocr", help="OCR engine (glm-ocr or qwen3-vl:8b)")
    o.add_argument("--fallback-engine", default="qwen3-vl:8b", help="Fallback OCR engine when the primary fails")
    o.add_argument("--dpi", type=int, default=150, help="DPI for scanned PDF pages (default: 150)")
    o.add_argument("--ollama-url", default=os.environ.get("CORNELL_KB_OLLAMA_URL", OLLAMA_URL), help="Ollama generate endpoint")

    # vision command
    v = sub.add_parser("vision", help="Analyze an image with Qwen3-VL")
    v.add_argument("image", help="Path to image file")
    v.add_argument("--prompt", default="Describe what you see in this image in detail.")
    v.add_argument("--ollama-url", default=os.environ.get("CORNELL_KB_OLLAMA_URL", OLLAMA_URL), help="Ollama generate endpoint")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.command == "transcribe":
        if args.engine == "whisper":
            transcribe_whisper(
                args.audio, args.output, args.model, device=args.device,
                compute_type=args.compute_type, reuse_model=args.reuse_model,
            )
        elif args.engine == "moss":
            transcribe_moss(
                args.audio, args.output, model_id=args.moss_model,
                device_preference=args.moss_device, reuse_model=args.reuse_model,
            )
    elif args.command == "ocr":
        if args.input.lower().endswith(".pdf"):
            ocr_pdf(
                args.input, args.output, engine=args.engine,
                fallback_engine=args.fallback_engine, render_dpi=args.dpi,
                ollama_url=args.ollama_url,
            )
        else:
            text = ocr_image(args.input, engine=args.engine, ollama_url=args.ollama_url)
            print(text)
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"\nSaved to {args.output}")
    elif args.command == "vision":
        text = vision_analyze(args.image, args.prompt, ollama_url=args.ollama_url)
        print(text)
    else:
        build_parser().print_help()


if __name__ == "__main__":
    main()
