#!/bin/bash
source $HOME/.local/bin/env
source ~/vllm-env/bin/activate

echo "=== Installing MOSS dependencies ==="
pip install -q git+https://github.com/OpenMOSS/MOSS-Transcribe-Diarize.git 2>&1

echo "=== Running MOSS transcription ==="
python3 << 'PYEOF'
import torch
import time
from transformers import AutoModelForCausalLM, AutoProcessor
from moss_transcribe_diarize import parse_transcript
from moss_transcribe_diarize.inference_utils import (
    build_transcription_messages,
    generate_transcription,
    resolve_device,
)

model_id = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
audio_path = "/mnt/c/Users/31163/Downloads/Test.m4a"

device = resolve_device("auto")
dtype = torch.bfloat16 if device.type == "cuda" else torch.float32
print(f"Device: {device}, dtype: {dtype}")

print("Loading MOSS model...")
model = AutoModelForCausalLM.from_pretrained(
    model_id, trust_remote_code=True, dtype="auto"
).to(dtype=dtype, device=device).eval()

processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

print("Transcribing...")
messages = build_transcription_messages(audio_path)

start = time.time()
result = generate_transcription(
    model, processor, messages,
    max_new_tokens=4096, do_sample=False, device=device, dtype=dtype,
)
elapsed = time.time() - start

print(f"\n=== MOSS Result ({elapsed:.1f}s) ===")
print(result["text"])

# Save to file
with open("/tmp/moss_result.txt", "w") as f:
    f.write(result["text"])

# Parse segments
print("\n=== Parsed Segments ===")
for segment in parse_transcript(result["text"]):
    print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.speaker} {segment.text}")

print(f"\nDone! {elapsed:.1f}s")
PYEOF
