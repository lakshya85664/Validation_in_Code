
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolStatus(str, Enum):
    OK = "ok"
    INVALID = "invalid"
    DENIED = "denied"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    CONFLICT = "conflict"
    NEEDS_APPROVAL = "needs_approval"


class NextAction(str, Enum):
    NONE = "none"
    CORRECT_ARGUMENTS = "correct_arguments"
    CHOOSE_REGISTERED_TOOL = "choose_registered_tool"
    REQUEST_AUTHORIZATION = "request_authorization"
    REQUEST_APPROVAL = "request_approval"
    RETRY_OR_REVIEW = "retry_or_review"
    CONTACT_SUPPORT = "contact_support"


class ToolCall(BaseModel):
    """Typed, validated representation of a requested tool invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    arguments: dict[str, Any]
    request_id: str = Field(min_length=1, max_length=100)


@dataclass
class ToolResult:
    """Standardized response returned by the tool gateway."""

    status: ToolStatus
    data: dict[str, Any] = field(default_factory=dict)
    next_action: NextAction = NextAction.NONE
    events: list[dict[str, Any]] = field(default_factory=list)
