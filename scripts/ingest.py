"""
Cornell KB — Hindsight Ingestion Script

Takes chunked facts (from chunker.py) and retains them into Hindsight
with structured metadata for searchable knowledge retrieval.

Usage:
    python ingest.py transcript_facts.json
    python ingest.py transcript_facts.json --dry-run
    python ingest.py --from-transcript transcript.txt --course "SYSEN 5100" --lecture 1
"""

import argparse
import json
import os
import sys
import urllib.request

HINDSIGHT_URL = "http://localhost:8888"


def hindsight_retain(content, context="", tags=None, bank_id="hermes-history", url=HINDSIGHT_URL):
    """Retain a fact into Hindsight memory."""
    item = {
        "content": content,
        "context": context,
    }
    if tags:
        item["tags"] = tags
    payload = {"items": [item]}

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{url}/v1/default/banks/{bank_id}/memories",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def hindsight_recall(query, top_k=10, tags=None, bank_id="hermes-history", url=HINDSIGHT_URL):
    """Search Hindsight memory."""
    payload = {
        "query": query,
        "top_k": top_k,
    }
    if tags:
        payload["tags"] = tags
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{url}/v1/default/banks/{bank_id}/memories/recall",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def format_fact_context(fact):
    """Build the context string for a fact's metadata."""
    parts = []
    if fact.get("course"):
        parts.append(f"{fact['course']}")
    if fact.get("course_name"):
        parts.append(f"({fact['course_name']})")
    if fact.get("lecture"):
        parts.append(f"Lecture #{fact['lecture']}")
    if fact.get("topic"):
        parts.append(f"— {fact['topic']}")
    if fact.get("source_type"):
        parts.append(f"[{fact['source_type']}]")
    if fact.get("timestamp_start") and fact.get("timestamp_end"):
        parts.append(f"@ {fact['timestamp_start']:.1f}s-{fact['timestamp_end']:.1f}s")
    return " ".join(parts)


def format_fact_tags(fact):
    """Build tags list for a fact."""
    tags = ["cornell-kb"]  # Always tag course content
    if fact.get("course"):
        tags.append(fact["course"].lower().replace(" ", "-"))
    if fact.get("topic"):
        tags.append(fact["topic"].lower().replace(" ", "-"))
    if fact.get("type"):
        tags.append(fact["type"])
    if fact.get("source_type"):
        tags.append(fact["source_type"])
    if fact.get("engine"):
        tags.append(fact["engine"])
    return tags


def ingest_facts(facts, dry_run=False, url=HINDSIGHT_URL):
    """Ingest a list of facts into Hindsight."""
    results = {"success": 0, "failed": 0, "errors": []}

    for i, fact in enumerate(facts):
        content = fact.get("content", "")
        if not content or len(content) < 20:
            print(f"  Skipping fact {i+1}: too short ({len(content)} chars)")
            results["failed"] += 1
            continue

        context = format_fact_context(fact)
        tags = format_fact_tags(fact)

        if dry_run:
            print(f"\n[DRY RUN] Fact {i+1}/{len(facts)}:")
            print(f"  Context: {context}")
            print(f"  Tags: {tags}")
            print(f"  Content: {content[:200]}...")
            results["success"] += 1
        else:
            result = hindsight_retain(content, context=context, tags=tags, url=url)
            if "error" in result:
                print(f"  Error on fact {i+1}: {result['error']}")
                results["failed"] += 1
                results["errors"].append(result["error"])
            else:
                results["success"] += 1
                if (i + 1) % 5 == 0:
                    print(f"  Ingested {i+1}/{len(facts)} facts...")

    return results


def main():
    parser = argparse.ArgumentParser(description="Ingest facts into Hindsight")
    parser.add_argument("facts_json", nargs="?", help="Path to facts JSON file (from chunker.py)")
    parser.add_argument("--dry-run", action="store_true", help="Print facts without ingesting")
    parser.add_argument("--hindsight-url", default=HINDSIGHT_URL, help="Hindsight API URL")
    parser.add_argument("--from-transcript", help="Run chunker + ingest in one step")
    parser.add_argument("--course", help="Course code (for --from-transcript)")
    parser.add_argument("--lecture", type=int, help="Lecture number (for --from-transcript)")
    parser.add_argument("--topic", help="Topic (for --from-transcript)")

    args = parser.parse_args()

    # If --from-transcript, run chunker first
    if args.from_transcript:
        if not args.course or args.lecture is None:
            print("Error: --course and --lecture required with --from-transcript")
            sys.exit(1)

        from chunker import chunk_transcript
        facts = chunk_transcript(
            args.from_transcript,
            args.course,
            args.lecture,
            topic=args.topic,
        )
        print(f"Chunked {len(facts)} facts from transcript")
    elif args.facts_json:
        with open(args.facts_json, "r", encoding="utf-8") as f:
            facts = json.load(f)
    else:
        print("Error: provide facts_json or --from-transcript")
        parser.print_help()
        sys.exit(1)

    # Ingest
    print(f"\nIngesting {len(facts)} facts into Hindsight...")
    results = ingest_facts(facts, dry_run=args.dry_run, url=args.hindsight_url)

    print(f"\n--- Results ---")
    print(f"Success: {results['success']}")
    print(f"Failed: {results['failed']}")
    if results["errors"]:
        print(f"Errors: {results['errors'][:3]}")


if __name__ == "__main__":
    main()
