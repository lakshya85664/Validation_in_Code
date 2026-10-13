
"""Gateway with validation, authorization, reliability, and audit events."""

from threading import Lock
from typing import Any

from src.contracts import NextAction, ToolCall, ToolResult, ToolStatus
from src.observability import emit_event
from src.providers import FakeProvider
from src.registry import ToolRegistry, ToolSpec
from src.reliability import IdempotencyStore, RateLimiter
from src.schemas import OrderLookupInput, RefundRequestInput
from src.validation import (
    OrderRecord,
    ValidationContext,
    ValidationPipeline,
)


class ToolGateway:
    def __init__(
        self,
        provider: FakeProvider | None = None,
        *,
        max_requests: int = 10,
        window_seconds: float = 60.0,
    ) -> None:
        self.provider = provider or FakeProvider()
        self.registry = ToolRegistry()
        self.rate_limiter = RateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        self.idempotency = IdempotencyStore()

        # Serializes the check/execute/store sequence in this process.
        self._execution_lock = Lock()

        self.registry.register(
            ToolSpec(
                name="order.lookup",
                version="1.0.0",
                description="Look up an order",
                input_model=OrderLookupInput,
                handler=self._lookup_handler,
                allowed_roles=frozenset({"support", "admin"}),
                access="read",
            )
        )
        self.registry.register(
            ToolSpec(
                name="refund.request",
                version="1.0.0",
                description="Submit a simulated refund request",
                input_model=RefundRequestInput,
                handler=self._refund_handler,
                allowed_roles=frozenset({"support", "admin"}),
                access="write",
                requires_approval=True,
            )
        )

        self.pipeline = ValidationPipeline(
            order_lookup=self._validation_order_lookup,
        )

    def _validation_order_lookup(
        self,
        order_id: str,
    ) -> OrderRecord | None:
        data = self.provider.lookup_order(order_id)
        if data is None:
            return None

        return OrderRecord(
            order_id=data["order_id"],
            status=data["status"],
            total_amount=float(data["total_amount"]),
            refundable=bool(data["refundable"]),
        )

    def _lookup_handler(self, **arguments: Any) -> dict[str, Any]:
        order = self.provider.lookup_order(arguments["order_id"])
        if order is None:
            raise LookupError("Order not found")
        return order

    def _refund_handler(self, **arguments: Any) -> dict[str, Any]:
        return self.provider.request_refund(**arguments)

    def _audit(
        self,
        call: ToolCall,
        status: ToolStatus,
        *,
        event: str = "tool.request.completed",
        stage: str | None = None,
    ) -> None:
        emit_event(
            event,
            request_id=call.request_id,
            tool=call.name,
            status=status.value,
            stage=stage,
        )

    def dispatch(
        self,
        call: ToolCall,
        *,
        role: str,
        evidence_verified: bool = False,
        approval_granted: bool = False,
    ) -> ToolResult:
        """Validate and authorize a request before invoking its handler."""

        spec = self.registry.get(call.name, call.version)

        if spec is None:
            result = ToolResult(
                status=ToolStatus.NOT_FOUND,
                next_action=NextAction.CHOOSE_REGISTERED_TOOL,
            )
            self._audit(call, result.status, stage="registry")
            return result

        if role not in spec.allowed_roles:
            result = ToolResult(
                status=ToolStatus.DENIED,
                next_action=NextAction.REQUEST_AUTHORIZATION,
            )
            self._audit(call, result.status, stage="authorization")
            return result

        # Rate limiting occurs before validation and provider execution.
        if not self.rate_limiter.allow(role):
            result = ToolResult(
                status=ToolStatus.RATE_LIMITED,
                next_action=NextAction.RETRY_OR_REVIEW,
            )
            self._audit(call, result.status, stage="rate_limit")
            return result

        # Serialize idempotency check through execution and result storage.
        with self._execution_lock:
            cached = self.idempotency.get(call.request_id)
            if cached is not None:
                try:
                    cached_status = ToolStatus(cached["status"])
                    cached_action = NextAction(cached["next_action"])
                except (KeyError, ValueError):
                    cached_status = ToolStatus.CONFLICT
                    cached_action = NextAction.RETRY_OR_REVIEW

                self._audit(
                    call,
                    cached_status,
                    event="tool.request.idempotency_replay",
                    stage="idempotency",
                )
                return ToolResult(
                    status=cached_status,
                    data=cached.get("data", {}),
                    next_action=cached_action,
                    events=cached.get("events", []),
                )

            validation = self.pipeline.validate(
                call.name,
                call.arguments,
                ValidationContext(
                    principal="gateway-authenticated-operator",
                    role=role,
                    evidence_verified=evidence_verified,
                    approval_granted=approval_granted,
                ),
            )

            if not validation.valid:
                if validation.requires_approval:
                    result = ToolResult(
                        status=ToolStatus.NEEDS_APPROVAL,
                        data={"errors": validation.errors},
                        next_action=NextAction.REQUEST_APPROVAL,
                        events=validation.events,
                    )
                else:
                    result = ToolResult(
                        status=ToolStatus.INVALID,
                        data={
                            "errors": validation.errors,
                            "stage": validation.stage,
                        },
                        next_action=NextAction.CORRECT_ARGUMENTS,
                        events=validation.events,
                    )

                # Do not cache invalid, denied, or approval-pending requests.
                self._audit(
                    call,
                    result.status,
                    event="tool.request.rejected",
                    stage=validation.stage,
                )
                return result

            try:
                output = spec.handler(**validation.normalized_data)
                result = ToolResult(
                    status=ToolStatus.OK,
                    data=output,
                    events=validation.events
                    + [
                        {
                            "event": "tool.execution.completed",
                            "tool": call.name,
                        }
                    ],
                )
            except LookupError:
                result = ToolResult(
                    status=ToolStatus.NOT_FOUND,
                    next_action=NextAction.CONTACT_SUPPORT,
                    events=validation.events,
                )
            except Exception:
                # Do not expose provider exception messages.
                result = ToolResult(
                    status=ToolStatus.FAILED,
                    next_action=NextAction.RETRY_OR_REVIEW,
                    events=validation.events,
                )

            # Cache terminal results so repeating the same request ID
            # cannot repeat an already completed simulated side effect.
            cached_result = self.idempotency.put_if_absent(
                call.request_id,
                {
                    "status": result.status.value,
                    "data": result.data,
                    "next_action": result.next_action.value,
                    "events": result.events,
                },
            )

            self._audit(
                call,
                result.status,
                stage="execution",
            )

            return ToolResult(
                status=ToolStatus(cached_result["status"]),
                data=cached_result.get("data", {}),
                next_action=NextAction(cached_result["next_action"]),
                events=cached_result.get("events", []),
            )
