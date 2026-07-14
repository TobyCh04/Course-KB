import os, time
nvidia_base = os.path.join(os.path.dirname(os.__file__), 'site-packages', 'nvidia')
if os.path.exists(nvidia_base):
    for dp, _, fn in os.walk(nvidia_base):
        if any(f.endswith('.dll') for f in fn):
            try: os.add_dll_directory(dp)
            except: pass
from faster_whisper import WhisperModel
print("Loading Whisper large-v3-turbo...")
model = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16')
print("Transcribing...")
start = time.time()
segs, info = model.transcribe('Test.m4a', language='en', beam_size=5)
parts = [f'[{s.start:.1f}-{s.end:.1f}] {s.text}' for s in segs]
elapsed = time.time() - start
print(f'WHISPER: {info.duration:.0f}s audio, {elapsed:.1f}s process, {info.duration/elapsed:.1f}x realtime')
print(f'{len(parts)} segments')
for p in parts[:20]: print(p)
if len(parts) > 20: print(f'... +{len(parts)-20} more')
with open('whisper_result.txt', 'w') as f: f.write('\n'.join(parts))
print('Saved to whisper_result.txt')
