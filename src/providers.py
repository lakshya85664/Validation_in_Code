
"""Fake provider for safe order and refund testing."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeProvider:
    orders: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "ORD-1001": {
                "order_id": "ORD-1001",
                "status": "delivered",
                "total_amount": 500.0,
                "refundable": True,
            },
            "ORD-1002": {
                "order_id": "ORD-1002",
                "status": "refunded",
                "total_amount": 250.0,
                "refundable": False,
            },
            "ORD-1003": {
                "order_id": "ORD-1003",
                "status": "delivered",
                "total_amount": 800.0,
                "refundable": True,
            },
        }
    )
    refund_requests: list[dict[str, Any]] = field(default_factory=list)

    def lookup_order(self, order_id: str) -> dict[str, Any] | None:
        """Return a copy so callers cannot mutate stored records."""
        order = self.orders.get(order_id)
        return dict(order) if order is not None else None

    def request_refund(
        self,
        order_id: str,
        amount: float,
        reason: str,
        customer_request: str,
    ) -> dict[str, Any]:
        """Record a simulated refund request; never move real money."""
        if order_id not in self.orders:
            raise LookupError("Order not found")

        request = {
            "refund_request_id": f"REF-{len(self.refund_requests) + 1:04d}",
            "order_id": order_id,
            "amount": amount,
            "reason": reason,
            "customer_request": customer_request,
            "status": "submitted_for_review",
        }
        self.refund_requests.append(request)

        return {
            "refund_request_id": request["refund_request_id"],
            "status": request["status"],
        }
