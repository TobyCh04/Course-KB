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
