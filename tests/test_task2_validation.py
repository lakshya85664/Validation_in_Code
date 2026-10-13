
import pytest

from src.validation import (
    OrderRecord,
    ValidationContext,
    ValidationPipeline,
)


ORDERS = {
    "ORD-1001": OrderRecord(
        order_id="ORD-1001",
        status="delivered",
        total_amount=500.0,
    ),
    "ORD-1002": OrderRecord(
        order_id="ORD-1002",
        status="refunded",
        total_amount=250.0,
    ),
    "ORD-1003": OrderRecord(
        order_id="ORD-1003",
        status="delivered",
        total_amount=500.0,
        refundable=False,
    ),
}


def lookup_order(order_id):
    return ORDERS.get(order_id)


def make_pipeline():
    return ValidationPipeline(
        order_lookup=lookup_order,
        refund_limit=100000.0,
    )


def valid_refund_arguments():
    return {
        "order_id": "ORD-1001",
        "amount": 250.0,
        "reason": "damaged",
        "customer_request": "The delivered item was damaged.",
    }


def verified_context(approval_granted=False):
    return ValidationContext(
        principal="operator-001",
        role="support",
        evidence_verified=True,
        approval_granted=approval_granted,
    )


def test_valid_order_lookup():
    result = make_pipeline().validate(
        "order.lookup",
        {"order_id": "ORD-1001", "channel": "web"},
        verified_context(),
    )

    assert result.valid is True
    assert result.stage == "complete"


def test_valid_refund_with_approval():
    result = make_pipeline().validate(
        "refund.request",
        valid_refund_arguments(),
        verified_context(approval_granted=True),
    )

    assert result.valid is True
    assert result.stage == "complete"


def test_refund_requires_approval():
    result = make_pipeline().validate(
        "refund.request",
        valid_refund_arguments(),
        verified_context(approval_granted=False),
    )

    assert result.valid is False
    assert result.stage == "approval"
    assert result.requires_approval is True


def test_refund_requires_verified_evidence():
    context = ValidationContext(
        principal="operator-001",
        role="support",
        evidence_verified=False,
        approval_granted=True,
    )

    result = make_pipeline().validate(
        "refund.request",
        valid_refund_arguments(),
        context,
    )

    assert result.valid is False
    assert result.stage == "evidence"


def test_unknown_tool_is_rejected():
    result = make_pipeline().validate(
        "refund.unknown",
        {},
        verified_context(),
    )

    assert result.valid is False
    assert result.stage == "tool_selection"


def test_invalid_schema_is_rejected():
    arguments = valid_refund_arguments()
    arguments["unexpected"] = "blocked"

    result = make_pipeline().validate(
        "refund.request",
        arguments,
        verified_context(approval_granted=True),
    )

    assert result.valid is False
    assert result.stage == "schema"
    assert result.errors


def test_order_not_found():
    arguments = valid_refund_arguments()
    arguments["order_id"] = "ORD-9999"

    result = make_pipeline().validate(
        "refund.request",
        arguments,
        verified_context(approval_granted=True),
    )

    assert result.valid is False
    assert result.errors[0]["code"] == "order_not_found"


def test_refunded_order_is_not_eligible():
    arguments = valid_refund_arguments()
    arguments["order_id"] = "ORD-1002"

    result = make_pipeline().validate(
        "refund.request",
        arguments,
        verified_context(approval_granted=True),
    )

    assert result.valid is False
    assert result.errors[0]["code"] == "order_status_not_eligible"


def test_non_refundable_order_is_rejected():
    arguments = valid_refund_arguments()
    arguments["order_id"] = "ORD-1003"

    result = make_pipeline().validate(
        "refund.request",
        arguments,
        verified_context(approval_granted=True),
    )

    assert result.valid is False
    assert result.errors[0]["code"] == "order_not_refundable"


def test_amount_cannot_exceed_order_total():
    arguments = valid_refund_arguments()
    arguments["amount"] = 501.0

    result = make_pipeline().validate(
        "refund.request",
        arguments,
        verified_context(approval_granted=True),
    )

    assert result.valid is False
    assert result.errors[0]["code"] == (
        "refund_amount_exceeds_allowed_limit"
    )


@pytest.mark.parametrize("amount", [0, -10, 100001])
def test_out_of_range_amount_fails_schema(amount):
    arguments = valid_refund_arguments()
    arguments["amount"] = amount

    result = make_pipeline().validate(
        "refund.request",
        arguments,
        verified_context(approval_granted=True),
    )

    assert result.valid is False
    assert result.stage == "schema"


def test_validation_emits_ordered_stage_events():
    result = make_pipeline().validate(
        "refund.request",
        valid_refund_arguments(),
        verified_context(approval_granted=True),
    )

    stages = [
        event.get("stage")
        for event in result.events
        if event["event"] == "validation.passed"
    ]

    assert stages == ["schema", "business", "evidence", "approval"]
    assert result.events[-1]["event"] == "validation.completed"
