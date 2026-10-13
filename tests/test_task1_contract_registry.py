
import pytest
from pydantic import ValidationError

from src.contracts import NextAction, ToolCall, ToolResult, ToolStatus
from src.registry import ToolRegistry, ToolSpec
from src.schemas import OrderLookupInput, RefundRequestInput


def lookup_handler(**kwargs):
    return {"found": True}


def make_spec():
    return ToolSpec(
        name="order.lookup",
        version="1.0.0",
        description="Look up an order",
        input_model=OrderLookupInput,
        handler=lookup_handler,
        allowed_roles=frozenset({"support", "admin"}),
        access="read",
    )


def test_valid_tool_call():
    call = ToolCall(
        name="order.lookup",
        version="1.0.0",
        arguments={
            "order_id": "ORD-1001",
            "channel": "web",
        },
        request_id="req-001",
    )

    assert call.name == "order.lookup"
    assert call.version == "1.0.0"


def test_tool_call_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ToolCall(
            name="order.lookup",
            version="1.0.0",
            arguments={},
            request_id="req-001",
            unexpected="blocked",
        )


def test_tool_call_rejects_invalid_version():
    with pytest.raises(ValidationError):
        ToolCall(
            name="order.lookup",
            version="latest",
            arguments={},
            request_id="req-001",
        )


def test_valid_order_schema():
    result = OrderLookupInput(
        order_id="ORD-1001",
        channel="web",
    )

    assert result.order_id == "ORD-1001"


def test_order_schema_rejects_invalid_identifier():
    with pytest.raises(ValidationError):
        OrderLookupInput(order_id="1001", channel="web")


def test_order_schema_rejects_unknown_channel():
    with pytest.raises(ValidationError):
        OrderLookupInput(
            order_id="ORD-1001",
            channel="telegram",
        )


def test_refund_schema_accepts_valid_request():
    result = RefundRequestInput(
        order_id="ORD-1001",
        amount=250.0,
        reason="damaged",
        customer_request="The delivered item was damaged.",
    )

    assert result.amount == 250.0


@pytest.mark.parametrize("amount", [0, -1, 100001])
def test_refund_schema_rejects_out_of_range_amount(amount):
    with pytest.raises(ValidationError):
        RefundRequestInput(
            order_id="ORD-1001",
            amount=amount,
            reason="damaged",
            customer_request="The delivered item was damaged.",
        )


def test_refund_schema_rejects_boolean_amount():
    with pytest.raises(ValidationError):
        RefundRequestInput(
            order_id="ORD-1001",
            amount=True,
            reason="damaged",
            customer_request="The delivered item was damaged.",
        )


def test_registry_registers_and_retrieves_tool():
    registry = ToolRegistry()
    spec = make_spec()

    registry.register(spec)

    assert registry.get("order.lookup", "1.0.0") is spec
    assert registry.get("missing.tool", "1.0.0") is None


def test_registry_rejects_duplicate_registration():
    registry = ToolRegistry()
    registry.register(make_spec())

    with pytest.raises(ValueError):
        registry.register(make_spec())


def test_registry_rejects_invalid_access_classification():
    registry = ToolRegistry()
    spec = make_spec()
    invalid_spec = ToolSpec(
        name=spec.name,
        version=spec.version,
        description=spec.description,
        input_model=spec.input_model,
        handler=spec.handler,
        allowed_roles=spec.allowed_roles,
        access="unknown",
    )

    with pytest.raises(ValueError):
        registry.register(invalid_spec)


def test_registry_description_does_not_expose_handler():
    registry = ToolRegistry()
    registry.register(make_spec())

    description = registry.describe()[0]

    assert description["name"] == "order.lookup"
    assert "handler" not in description


def test_tool_result_has_consistent_contract():
    result = ToolResult(
        status=ToolStatus.DENIED,
        next_action=NextAction.REQUEST_AUTHORIZATION,
    )

    assert result.status == ToolStatus.DENIED
    assert result.next_action == NextAction.REQUEST_AUTHORIZATION
    assert result.data == {}
