
from src.contracts import ToolCall, ToolStatus
from src.gateway import ToolGateway
from src.providers import FakeProvider


def make_refund_call(request_id="refund-001"):
    return ToolCall(
        name="refund.request",
        version="1.0.0",
        request_id=request_id,
        arguments={
            "order_id": "ORD-1001",
            "amount": 200.0,
            "reason": "damaged",
            "customer_request": "The delivered item was damaged.",
        },
    )


def make_lookup_call(request_id="lookup-001"):
    return ToolCall(
        name="order.lookup",
        version="1.0.0",
        request_id=request_id,
        arguments={
            "order_id": "ORD-1001",
            "channel": "web",
        },
    )


def test_duplicate_refund_request_executes_only_once():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    first = gateway.dispatch(
        make_refund_call("same-request"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )
    second = gateway.dispatch(
        make_refund_call("same-request"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.OK
    assert first.data == second.data
    assert len(provider.refund_requests) == 1


def test_rate_limited_request_does_not_execute():
    provider = FakeProvider()
    gateway = ToolGateway(provider, max_requests=1, window_seconds=60)

    first = gateway.dispatch(
        make_refund_call("refund-first"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )
    second = gateway.dispatch(
        make_refund_call("refund-second"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.RATE_LIMITED
    assert len(provider.refund_requests) == 1


def test_approval_pending_request_can_be_retried_after_approval():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    pending = gateway.dispatch(
        make_refund_call("approval-retry"),
        role="support",
        evidence_verified=True,
        approval_granted=False,
    )
    approved = gateway.dispatch(
        make_refund_call("approval-retry"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )

    assert pending.status == ToolStatus.NEEDS_APPROVAL
    assert approved.status == ToolStatus.OK
    assert len(provider.refund_requests) == 1


def test_different_request_ids_are_distinct():
    provider = FakeProvider()
    gateway = ToolGateway(provider)

    first = gateway.dispatch(
        make_refund_call("refund-A"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )
    second = gateway.dispatch(
        make_refund_call("refund-B"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.OK
    assert len(provider.refund_requests) == 2


def test_rate_limit_is_separate_for_roles():
    gateway = ToolGateway(max_requests=1, window_seconds=60)

    first = gateway.dispatch(
        make_lookup_call("lookup-support"),
        role="support",
    )
    second = gateway.dispatch(
        make_lookup_call("lookup-admin"),
        role="admin",
    )

    assert first.status == ToolStatus.OK
    assert second.status == ToolStatus.OK
