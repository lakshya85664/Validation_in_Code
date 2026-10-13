
"""Export Pydantic input schemas for the assessment."""

import json
from pathlib import Path

from src.schemas import OrderLookupInput, RefundRequestInput


ROOT = Path(__file__).resolve().parent
SCHEMA_DIR = ROOT / "schemas"


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    schemas = {
        "order_lookup_input.json": OrderLookupInput.model_json_schema(),
        "refund_request_input.json": RefundRequestInput.model_json_schema(),
    }

    for filename, schema in schemas.items():
        destination = SCHEMA_DIR / filename
        destination.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Created: {destination.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
