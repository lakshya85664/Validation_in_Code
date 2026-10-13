
"""Central validation pipeline for order and refund tool requests."""

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from src.schemas import OrderLookupInput, RefundRequestInput


@dataclass
class ValidationResult:
    """Structured result of validating a tool request."""

    valid: bool
    stage: str
    errors: list[dict[str, Any]] = field(default_factory=list)
    normalized_data: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationContext:
    """Trusted facts supplied by the gateway, not by tool arguments."""

    principal: str
    role: str
    approval_granted: bool = False
    evidence_verified: bool = False


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    status: str
    total_amount: float
    refundable: bool = True


class ValidationPipeline:
    """Run schema, business, evidence, and approval checks in order."""

    def __init__(
        self,
        order_lookup: Callable[[str], OrderRecord | None],
        refund_limit: float = 100000.0,
    ) -> None:
        self.order_lookup = order_lookup
        self.refund_limit = refund_limit

    def validate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ValidationContext,
    ) -> ValidationResult:
        events: list[dict[str, Any]] = [
            {"event": "validation.started", "tool": tool_name}
        ]

        models: dict[str, type[BaseModel]] = {
            "order.lookup": OrderLookupInput,
            "refund.request": RefundRequestInput,
        }

        model = models.get(tool_name)
        if model is None:
            return self._failure(
                "tool_selection",
                "unknown_tool",
                events,
            )

        # Stage 1: strict syntax/schema validation.
        try:
            parsed = model.model_validate(arguments)
        except ValidationError as exc:
            errors = [
                {
                    "field": ".".join(str(part) for part in item["loc"]),
                    "type": item["type"],
                    "message": item["msg"],
                }
                for item in exc.errors()
            ]
            events.append(
                {"event": "validation.rejected", "stage": "schema"}
            )
            return ValidationResult(
                valid=False,
                stage="schema",
                errors=errors,
                events=events,
            )

        data = parsed.model_dump()
        events.append({"event": "validation.passed", "stage": "schema"})

        # Read-only lookup does not require refund-specific checks.
        if tool_name == "order.lookup":
            events.append(
                {"event": "validation.passed", "stage": "business"}
            )
            return ValidationResult(
                valid=True,
                stage="complete",
                normalized_data=data,
                events=events
                + [{"event": "validation.completed", "valid": True}],
            )

        # Stage 2: business rules using trusted provider data.
        order = self.order_lookup(data["order_id"])

        if order is None:
            return self._failure(
                "business",
                "order_not_found",
                events,
                data,
            )

        if not order.refundable:
            return self._failure(
                "business",
                "order_not_refundable",
                events,
                data,
            )

        if order.status in {"cancelled", "refunded", "chargeback"}:
            return self._failure(
                "business",
                "order_status_not_eligible",
                events,
                data,
            )

        if data["amount"] > min(order.total_amount, self.refund_limit):
            return self._failure(
                "business",
                "refund_amount_exceeds_allowed_limit",
                events,
                data,
            )

        events.append({"event": "validation.passed", "stage": "business"})

        # Stage 3: evidence must be independently verified.
        if not context.evidence_verified:
            return self._failure(
                "evidence",
                "verified_customer_evidence_required",
                events,
                data,
            )

        events.append({"event": "validation.passed", "stage": "evidence"})

        # Stage 4: refunds need a separate approval decision.
        if not context.approval_granted:
            events.append(
                {
                    "event": "validation.needs_approval",
                    "stage": "approval",
                }
            )
            return ValidationResult(
                valid=False,
                stage="approval",
                errors=[{"code": "approval_required"}],
                normalized_data=data,
                requires_approval=True,
                events=events,
            )

        events.append({"event": "validation.passed", "stage": "approval"})
        events.append({"event": "validation.completed", "valid": True})

        return ValidationResult(
            valid=True,
            stage="complete",
            normalized_data=data,
            events=events,
        )

    @staticmethod
    def _failure(
        stage: str,
        code: str,
        events: list[dict[str, Any]],
        data: dict[str, Any] | None = None,
    ) -> ValidationResult:
        events.append(
            {"event": "validation.rejected", "stage": stage, "code": code}
        )
        return ValidationResult(
            valid=False,
            stage=stage,
            errors=[{"code": code}],
            normalized_data=data or {},
            events=events,
        )
