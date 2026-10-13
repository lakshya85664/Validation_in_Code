
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class OrderLookupInput(StrictInput):
    order_id: str = Field(
        min_length=8,
        max_length=20,
        pattern=r"^ORD-\d{4,16}$",
    )
    channel: Literal["web", "mobile", "support"]


class RefundRequestInput(StrictInput):
    order_id: str = Field(
        min_length=8,
        max_length=20,
        pattern=r"^ORD-\d{4,16}$",
    )
    amount: float = Field(gt=0, le=100000)
    reason: Literal[
        "duplicate",
        "damaged",
        "not_delivered",
        "other",
    ]
    customer_request: str = Field(min_length=10, max_length=500)

    @field_validator("amount", mode="before")
    @classmethod
    def reject_boolean_amount(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("amount must be a number, not a boolean")
        return value
