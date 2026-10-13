
import json
import logging

import pytest

from src.observability import emit_event
from src.reliability import IdempotencyStore, RateLimiter


def test_rate_limiter_allows_requests_within_limit():
    limiter = RateLimiter(max_requests=2, window_seconds=60)

    assert limiter.allow("operator-1") is True
    assert limiter.allow("operator-1") is True
    assert limiter.allow("operator-1") is False


def test_rate_limiter_separates_keys():
    limiter = RateLimiter(max_requests=1, window_seconds=60)

    assert limiter.allow("operator-1") is True
    assert limiter.allow("operator-1") is False
    assert limiter.allow("operator-2") is True


def test_rate_limiter_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        RateLimiter(max_requests=0)

    with pytest.raises(ValueError):
        RateLimiter(window_seconds=0)


def test_idempotency_store_returns_existing_result():
    store = IdempotencyStore()

    first = store.put_if_absent(
        "request-1",
        {"status": "ok", "request_number": 1},
    )
    second = store.put_if_absent(
        "request-1",
        {"status": "ok", "request_number": 2},
    )

    assert first["request_number"] == 1
    assert second["request_number"] == 1
    assert store.size() == 1


def test_idempotency_store_returns_copies():
    store = IdempotencyStore()
    store.put_if_absent("request-1", {"status": "ok"})

    result = store.get("request-1")
    result["status"] = "modified"

    assert store.get("request-1") == {"status": "ok"}


def test_idempotency_store_handles_different_keys():
    store = IdempotencyStore()

    store.put_if_absent("request-1", {"status": "ok"})
    store.put_if_absent("request-2", {"status": "denied"})

    assert store.size() == 2
    assert store.get("request-1")["status"] == "ok"
    assert store.get("request-2")["status"] == "denied"


def test_structured_event_is_json_and_excludes_arguments(caplog):
    with caplog.at_level(logging.INFO, logger="validation_gateway"):
        event = emit_event(
            "tool.execution.completed",
            request_id="req-001",
            tool="order.lookup",
            status="ok",
            stage="execution",
        )

    parsed = json.loads(caplog.records[-1].message)

    assert parsed == event
    assert parsed["request_id"] == "req-001"
    assert "arguments" not in parsed
    assert "customer_request" not in parsed
