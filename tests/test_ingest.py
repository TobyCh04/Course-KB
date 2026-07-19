import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _fact(number):
    return {
        "content": f"Fact {number}: " + "important detail " * 3,
        "course": "TEST 1000",
        "lecture": 1,
        "topic": "batching",
        "type": "concept",
        "source_type": "lecture",
    }


def test_ingest_facts_sends_valid_facts_in_configured_batches():
    from scripts.ingest import ingest_facts

    class FakeHindsightClient:
        def __init__(self):
            self.calls = []

        def post_json(self, url, payload, **kwargs):
            self.calls.append((url, payload, kwargs))
            return {"stored": len(payload["items"])}

    client = FakeHindsightClient()
    results = ingest_facts([_fact(1), _fact(2), _fact(3)], batch_size=2, client=client)

    assert results["success"] == 3
    assert results["failed"] == 0
    assert results["batches_succeeded"] == 2
    assert [len(call[1]["items"]) for call in client.calls] == [2, 1]
    assert all(set(call[1]) == {"items"} for call in client.calls)


def test_ingest_facts_reports_only_the_failed_batch_and_continues():
    from scripts.ingest import ingest_facts

    class FakeHindsightClient:
        def __init__(self):
            self.calls = 0

        def post_json(self, _url, _payload, **_kwargs):
            self.calls += 1
            return {"error": "batch rejected"} if self.calls == 1 else {"stored": 1}

    results = ingest_facts(
        [_fact(1), _fact(2), _fact(3)], batch_size=2, client=FakeHindsightClient()
    )

    assert results["success"] == 1
    assert results["failed"] == 2
    assert results["batches_succeeded"] == 1
    assert results["batches_failed"] == 1
    assert [item["index"] for item in results["failed_items"]] == [1, 2]
    assert {item["status"] for item in results["failed_items"]} == {"unconfirmed"}


def test_format_fact_tags_include_namespaced_metadata():
    from scripts.ingest import format_fact_tags

    tags = format_fact_tags({
        **_fact(1),
        "semester": "Fall 2026",
        "date": "2026-09-01",
    })

    assert "cornell-kb" in tags
    assert "course:test-1000" in tags
    assert "lecture:1" in tags
    assert "source-type:lecture" in tags
    assert "scope:course" in tags
    assert "semester:fall-2026" in tags
    assert "date:2026-09-01" in tags


def test_hindsight_recall_translates_filters_to_strict_tag_payload():
    from scripts.ingest import hindsight_recall

    class FakeHindsightClient:
        def __init__(self):
            self.payload = None

        def post_json(self, _url, payload, **_kwargs):
            self.payload = payload
            return {"results": []}

    client = FakeHindsightClient()
    hindsight_recall(
        "kanban",
        filters={
            "course": "TEST 1000",
            "lecture": 1,
            "source_scope": "course",
            "semester": "Fall 2026",
            "date": "2026-09-01",
        },
        client=client,
    )

    assert client.payload["tags"] == [
        "cornell-kb",
        "course:test-1000",
        "lecture:1",
        "scope:course",
        "semester:fall-2026",
        "date:2026-09-01",
    ]
    assert client.payload["tags_match"] == "all_strict"
