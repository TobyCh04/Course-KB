import os, time, torch
from transformers import AutoModelForCausalLM, AutoProcessor
from moss_transcribe_diarize import parse_transcript
from moss_transcribe_diarize.inference_utils import (
    build_transcription_messages, generate_transcription, resolve_device,
)

print("Loading MOSS-Transcribe-Diarize 0.9B...")
model_id = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
device = resolve_device("auto")
dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
print(f"Device: {device}, dtype: {dtype}")

start_load = time.time()
model = AutoModelForCausalLM.from_pretrained(
    model_id, trust_remote_code=True, dtype="auto"
).to(dtype=dtype).to(device).eval()
processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
print(f"Model loaded in {time.time() - start_load:.1f}s")

print("Transcribing...")
messages = build_transcription_messages("Test.m4a")
start = time.time()
result = generate_transcription(model, processor, messages, max_new_tokens=16384)
elapsed = time.time() - start

parsed = parse_transcript(result)
speakers = set()
for seg in parsed:
    if seg.get("speaker"):
        speakers.add(seg["speaker"])

lines = []
for seg in parsed:
    spk = seg.get("speaker", "?")
    s = seg.get("start", 0)
    e = seg.get("end", 0)
    t = seg.get("text", "")
    lines.append(f"[{s:.1f}-{e:.1f}][{spk}] {t}")

print(f"MOSS: {elapsed:.1f}s process, {len(parsed)} segments, {len(speakers)} speakers")
for l in lines[:20]:
    print(l)
if len(lines) > 20:
    print(f"... +{len(lines)-20} more")
with open("moss_result.txt", "w") as f:
    f.write("\n".join(lines))
print("Saved to moss_result.txt")
