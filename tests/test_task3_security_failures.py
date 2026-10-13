
import pytest

from src.contracts import ToolCall, ToolStatus
from src.gateway import ToolGateway
from src.providers import FakeProvider


def make_call(name, arguments, version="1.0.0", request_id="req-001"):
    return ToolCall(
        name=name,
        version=version,
        arguments=arguments,
        request_id=request_id,
    )


def refund_arguments():
    return {
        "order_id": "ORD-1001",
        "amount": 200.0,
        "reason": "damaged",
        "customer_request": "The delivered item was damaged.",
    }


def test_unknown_tool_is_rejected():
    gateway = ToolGateway()

    result = gateway.dispatch(
        make_call("unknown.tool", {}),
        role="admin",
    )

    assert result.status == ToolStatus.NOT_FOUND


def test_unknown_version_is_rejected():
    gateway = ToolGateway()

    result = gateway.dispatch(
        make_call(
            "order.lookup",
            {"order_id": "ORD-1001", "channel": "web"},
            version="9.9.9",
        ),
        role="support",
    )

    assert result.status == ToolStatus.NOT_FOUND


def test_unauthorized_role_cannot_lookup_order():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    result = gateway.dispatch(
        make_call(
            "order.lookup",
            {"order_id": "ORD-1001", "channel": "web"},
        ),
        role="guest",
    )

    assert result.status == ToolStatus.DENIED
    assert provider.refund_requests == []


def test_invalid_refund_does_not_execute():
    provider = FakeProvider()
    gateway = ToolGateway(provider)
    arguments = refund_arguments()
    arguments["amount"] = 9000.0

    result = gateway.dispatch(
        make_call("refund.request", arguments),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )

    assert result.status == ToolStatus.INVALID
    assert provider.refund_requests == []


def test_missing_evidence_prevents_refund_execution():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    result = gateway.dispatch(
        make_call("refund.request", refund_arguments()),
        role="support",
        evidence_verified=False,
        approval_granted=True,
    )

    assert result.status == ToolStatus.INVALID
    assert provider.refund_requests == []


def test_missing_approval_prevents_refund_execution():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    result = gateway.dispatch(
        make_call("refund.request", refund_arguments()),
        role="support",
        evidence_verified=True,
        approval_granted=False,
    )

    assert result.status == ToolStatus.NEEDS_APPROVAL
    assert provider.refund_requests == []


def test_valid_approved_refund_is_recorded_once():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    result = gateway.dispatch(
        make_call("refund.request", refund_arguments()),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )

    assert result.status == ToolStatus.OK
    assert result.data["status"] == "submitted_for_review"
    assert len(provider.refund_requests) == 1


@pytest.mark.parametrize("role", ["guest", "viewer", ""])
def test_non_privileged_roles_cannot_submit_refund(role):
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    result = gateway.dispatch(
        make_call("refund.request", refund_arguments()),
        role=role,
        evidence_verified=True,
        approval_granted=True,
    )

    assert result.status == ToolStatus.DENIED
    assert provider.refund_requests == []


def test_provider_error_is_not_exposed_to_caller():
    class BrokenProvider(FakeProvider):
        def lookup_order(self, order_id):
            raise RuntimeError("sensitive internal provider details")

    gateway = ToolGateway(BrokenProvider())

    result = gateway.dispatch(
        make_call(
            "order.lookup",
            {"order_id": "ORD-1001", "channel": "web"},
        ),
        role="support",
    )

    assert result.status == ToolStatus.FAILED
    assert "sensitive internal provider details" not in str(result.data)
