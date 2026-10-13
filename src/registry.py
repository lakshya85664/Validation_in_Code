
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[..., dict[str, Any]]
    allowed_roles: frozenset[str]
    access: str  # "read" or "write"
    requires_approval: bool = False


class ToolRegistry:
    """Explicit registry of supported tool names and versions."""

    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        key = (spec.name, spec.version)

        if key in self._tools:
            raise ValueError(
                f"Tool already registered: {spec.name}@{spec.version}"
            )

        if spec.access not in {"read", "write"}:
            raise ValueError("Tool access must be 'read' or 'write'")

        self._tools[key] = spec

    def get(self, name: str, version: str) -> ToolSpec | None:
        return self._tools.get((name, version))

    def describe(self) -> list[dict[str, Any]]:
        """Return registry metadata without exposing handlers."""
        return [
            {
                "name": spec.name,
                "version": spec.version,
                "description": spec.description,
                "input_schema": spec.input_model.model_json_schema(),
                "allowed_roles": sorted(spec.allowed_roles),
                "access": spec.access,
                "requires_approval": spec.requires_approval,
            }
            for spec in sorted(
                self._tools.values(),
                key=lambda item: (item.name, item.version),
            )
        ]