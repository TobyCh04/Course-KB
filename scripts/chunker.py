"""
Cornell KB — Transcript Chunking Script

Takes a transcript (from Whisper/MOSS) and extracts discrete study facts
using an LLM. Each fact is self-contained, searchable, and tagged with metadata.

Usage:
    python chunker.py transcript.txt --course "SYSEN 5100" --lecture 1 --topic "closed-loop control"
    python chunker.py transcript.txt --course "SYSEN 5100" --lecture 1 --auto-detect
"""

import argparse
import json
import os
import re
import sys
import urllib.request

# Ollama API on the laptop
OLLAMA_URL = "http://100.104.205.105:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"  # Text model for chunking


CHUNKING_PROMPT = """You are processing a lecture transcript for {course_name} ({course_code}).
Lecture #{lecture}: {topic}

Extract key study facts from this transcript segment. Each fact should be:
- Self-contained (understandable without surrounding context)
- Focused on one concept, formula, example, or definition
- Include technical terms for searchability
- Preserve professor examples and explanations (like the dishwasher or car examples)
- For formulas/equations, include them in standard notation

Output EXACTLY in this format (one block per fact):
---FACT---
TOPIC: <topic tag>
TYPE: <text|formula|example|definition>
CONTENT: <the fact, 50-200 words>
---END---

If the segment contains no meaningful facts (filler, transitions, etc.), output:
---SKIP---

Transcript segment:
{segment}
"""


def call_ollama(prompt, model=DEFAULT_MODEL, url=OLLAMA_URL):
    """Call Ollama API and return the response text."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 4096}
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")


def split_transcript(text, max_chars=3000):
    """Split transcript into segments by timestamp boundaries."""
    # Parse timestamp format: [start -> end] text
    lines = text.strip().split("\n")
    segments = []
    current_segment = []
    current_len = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # If adding this line would exceed limit, flush current segment
        if current_len + len(line) > max_chars and current_segment:
            segments.append("\n".join(current_segment))
            current_segment = []
            current_len = 0

        current_segment.append(line)
        current_len += len(line)

    if current_segment:
        segments.append("\n".join(current_segment))

    return segments


def extract_timestamp_range(segment_text):
    """Extract start/end timestamps from a segment."""
    timestamps = re.findall(r'\[(\d+\.\d+)s\s*->\s*(\d+\.\d+)s\]', segment_text)
    if timestamps:
        return float(timestamps[0][0]), float(timestamps[-1][1])
    return None, None


def parse_facts(llm_response):
    """Parse the LLM response into structured facts."""
    facts = []
    blocks = llm_response.split("---FACT---")

    for block in blocks:
        block = block.strip()
        if not block or "---SKIP---" in block:
            continue

        # Remove trailing ---END---
        block = re.sub(r'---END---.*', '', block, flags=re.DOTALL).strip()

        # Extract fields
        topic_match = re.search(r'TOPIC:\s*(.+?)(?:\n|$)', block)
        type_match = re.search(r'TYPE:\s*(.+?)(?:\n|$)', block)
        content_match = re.search(r'CONTENT:\s*(.+?)(?=TOPIC:|TYPE:|$)', block, re.DOTALL)

        if content_match:
            facts.append({
                "topic": topic_match.group(1).strip() if topic_match else "general",
                "type": type_match.group(1).strip() if type_match else "text",
                "content": content_match.group(1).strip(),
            })

    return facts


def chunk_transcript(transcript_path, course_code, lecture, topic=None, model=DEFAULT_MODEL, course_catalog=None, ollama_url=None):
    """Main chunking function. Returns list of structured facts."""
    if ollama_url is None:
        ollama_url = OLLAMA_URL
    # Read transcript
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    # Load course info from catalog
    course_name = course_code
    if course_catalog:
        for code, info in course_catalog.items():
            if code.upper() == course_code.upper():
                course_name = info.get("name", course_code)
                break

    # Auto-detect topic from first few lines if not provided
    if topic is None:
        topic = "lecture content"

    # Split into segments
    segments = split_transcript(transcript)
    print(f"Split transcript into {len(segments)} segments")

    all_facts = []
    for i, segment in enumerate(segments):
        print(f"\nProcessing segment {i+1}/{len(segments)}...")

        # Extract timestamp range
        start_time, end_time = extract_timestamp_range(segment)

        # Build prompt
        prompt = CHUNKING_PROMPT.format(
            course_name=course_name,
            course_code=course_code,
            lecture=lecture,
            topic=topic,
            segment=segment,
        )

        # Call LLM
        try:
            response = call_ollama(prompt, model=model, url=ollama_url)
            facts = parse_facts(response)

            # Add metadata to each fact
            for fact in facts:
                fact["course"] = course_code
                fact["course_name"] = course_name
                fact["lecture"] = lecture
                fact["source_type"] = "lecture"
                fact["timestamp_start"] = start_time
                fact["timestamp_end"] = end_time
                fact["source_file"] = os.path.basename(transcript_path)
                fact["engine"] = "whisper" if "whisper" in transcript_path.lower() else "moss"

            all_facts.extend(facts)
            print(f"  Extracted {len(facts)} facts")

        except Exception as e:
            print(f"  Error: {e}")
            continue

    return all_facts


def main():
    parser = argparse.ArgumentParser(description="Chunk transcript into study facts")
    parser.add_argument("transcript", help="Path to transcript file")
    parser.add_argument("--course", required=True, help="Course code (e.g., SYSEN 5100)")
    parser.add_argument("--lecture", type=int, required=True, help="Lecture number")
    parser.add_argument("--topic", default=None, help="Topic name (auto-detected if omitted)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model for chunking")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama API URL")

    args = parser.parse_args()

    ollama_url = args.ollama_url

    # Load course catalog
    catalog_path = os.path.join(os.path.dirname(__file__), "config", "course_catalog.yaml")
    catalog = None
    if os.path.exists(catalog_path):
        try:
            import yaml
            with open(catalog_path, "r") as f:
                catalog = yaml.safe_load(f).get("courses", {})
        except ImportError:
            print("Note: install pyyaml for course catalog support")

    # Chunk
    facts = chunk_transcript(
        args.transcript,
        args.course,
        args.lecture,
        topic=args.topic,
        model=args.model,
        course_catalog=catalog,
        ollama_url=ollama_url,
    )

    print(f"\nTotal facts extracted: {len(facts)}")

    # Save
    if args.output:
        output_path = args.output
    else:
        base = os.path.splitext(os.path.basename(args.transcript))[0]
        output_path = os.path.join(os.path.dirname(args.transcript), f"{base}_facts.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_path}")

    # Print summary
    print("\n--- Summary ---")
    for i, fact in enumerate(facts[:5]):
        print(f"\nFact {i+1} [{fact['type']}] ({fact['topic']}):")
        print(f"  {fact['content'][:150]}...")
    if len(facts) > 5:
        print(f"\n... and {len(facts) - 5} more facts")


if __name__ == "__main__":
    main()
