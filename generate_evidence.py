
"""Generate reproducible evidence and an operator report."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.contracts import ToolCall
from src.gateway import ToolGateway
from src.providers import FakeProvider


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
TRACES = ROOT / "traces"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def make_call(name, arguments, request_id, version="1.0.0"):
    return ToolCall(
        name=name,
        version=version,
        arguments=arguments,
        request_id=request_id,
    )


def result_to_dict(result):
    return {
        "status": result.status.value,
        "data": result.data,
        "next_action": result.next_action.value,
        "events": result.events,
    }


def run_scenario(name, gateway, call, **kwargs):
    result = gateway.dispatch(call, **kwargs)
    record = {
        "scenario": name,
        "source": "actual_gateway_execution",
        "request": call.model_dump(mode="json"),
        "result": result_to_dict(result),
    }
    write_json(TRACES / f"{name}.json", record)
    return {
        "scenario": name,
        "expected_status": kwargs.pop("_expected_status", None),
        "actual_status": result.status.value,
        "passed": result.status.value == kwargs.pop(
            "_expected_status_fallback", result.status.value
        ),
    }


def run_and_record(name, gateway, call, expected_status, **kwargs):
    result = gateway.dispatch(call, **kwargs)
    record = {
        "scenario": name,
        "source": "actual_gateway_execution",
        "request": call.model_dump(mode="json"),
        "result": result_to_dict(result),
        "expected_status": expected_status,
        "passed": result.status.value == expected_status,
    }
    write_json(TRACES / f"{name}.json", record)
    print(
        f"{name}: expected={expected_status}, "
        f"actual={result.status.value}, "
        f"passed={record['passed']}"
    )
    return record


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    TRACES.mkdir(parents=True, exist_ok=True)

    print("Topic 5 — Evidence Generation")
    print("=" * 45)

    # Run the actual automated test suite and save its output.
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    test_output = completed.stdout + completed.stderr
    (EVIDENCE / "full_test_output.txt").write_text(
        test_output,
        encoding="utf-8",
    )
    print(test_output.strip() or "(pytest produced no output)")

    scenarios = []

    # Valid order lookup.
    scenarios.append(
        run_and_record(
            "task5_valid_lookup",
            ToolGateway(),
            make_call(
                "order.lookup",
                {"order_id": "ORD-1001", "channel": "web"},
                "evidence-lookup-001",
            ),
            "ok",
            role="support",
        )
    )

    # Invalid schema must be rejected before execution.
    scenarios.append(
        run_and_record(
            "task5_invalid_input",
            ToolGateway(),
            make_call(
                "refund.request",
                {
                    "order_id": "ORD-1001",
                    "amount": 0,
                    "reason": "damaged",
                    "customer_request": "The item was damaged.",
                },
                "evidence-invalid-001",
            ),
            "invalid",
            role="support",
            evidence_verified=True,
            approval_granted=True,
        )
    )

    # Unauthorized access.
    scenarios.append(
        run_and_record(
            "task5_unauthorized_refund",
            ToolGateway(),
            make_call(
                "refund.request",
                {
                    "order_id": "ORD-1001",
                    "amount": 200,
                    "reason": "damaged",
                    "customer_request": "The delivered item was damaged.",
                },
                "evidence-denied-001",
            ),
            "denied",
            role="guest",
            evidence_verified=True,
            approval_granted=True,
        )
    )

    # Approval gate.
    scenarios.append(
        run_and_record(
            "task5_approval_required",
            ToolGateway(),
            make_call(
                "refund.request",
                {
                    "order_id": "ORD-1001",
                    "amount": 200,
                    "reason": "damaged",
                    "customer_request": "The delivered item was damaged.",
                },
                "evidence-approval-001",
            ),
            "needs_approval",
            role="support",
            evidence_verified=True,
            approval_granted=False,
        )
    )

    # Rate limiting: one request allowed, second rejected.
    limited_gateway = ToolGateway(max_requests=1, window_seconds=60)
    limited_provider = limited_gateway.provider

    scenarios.append(
        run_and_record(
            "task5_rate_limit",
            limited_gateway,
            make_call(
                "refund.request",
                {
                    "order_id": "ORD-1001",
                    "amount": 200,
                    "reason": "damaged",
                    "customer_request": "The delivered item was damaged.",
                },
                "evidence-rate-001",
            ),
            "rate_limited",
            role="support",
            evidence_verified=True,
            approval_granted=True,
        )
        if limited_gateway.rate_limiter.allow("support")
        else {
            "scenario": "task5_rate_limit",
            "expected_status": "rate_limited",
            "actual_status": "not_run",
            "passed": False,
        }
    )

    # Run a dedicated rate-limit scenario with deterministic setup.
    rate_gateway = ToolGateway(max_requests=1, window_seconds=60)
    rate_args = {
        "order_id": "ORD-1001",
        "amount": 200,
        "reason": "damaged",
        "customer_request": "The delivered item was damaged.",
    }
    rate_gateway.dispatch(
        make_call("refund.request", rate_args, "rate-prime"),
        role="support",
        evidence_verified=True,
        approval_granted=True,
    )
    scenarios.append(
        run_and_record(
            "task5_rate_limit_verified",
            rate_gateway,
            make_call("refund.request", rate_args, "rate-blocked"),
            "rate_limited",
            role="support",
            evidence_verified=True,
            approval_granted=True,
        )
    )

    # Successful approved simulated refund request.
    success_provider = FakeProvider()
    scenarios.append(
        run_and_record(
            "task5_approved_refund",
            ToolGateway(success_provider),
            make_call(
                "refund.request",
                {
                    "order_id": "ORD-1001",
                    "amount": 200,
                    "reason": "damaged",
                    "customer_request": "The delivered item was damaged.",
                },
                "evidence-refund-001",
            ),
            "ok",
            role="support",
            evidence_verified=True,
            approval_granted=True,
        )
    )

    passed_scenarios = sum(item["passed"] for item in scenarios)
    report = {
        "assessment": "Topic 5 — Validation in Code",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "test_suite": {
            "command": "python -m pytest -q",
            "exit_code": completed.returncode,
            "passed": completed.returncode == 0,
            "output_file": "evidence/full_test_output.txt",
        },
        "scenarios": {
            "total": len(scenarios),
            "passed": passed_scenarios,
            "failed": len(scenarios) - passed_scenarios,
            "details": scenarios,
        },
        "limitations": [
            "The provider is a fake provider; no real refunds are issued.",
            "Rate limiting and idempotency use in-memory process-local storage.",
            "The report records the test-suite run that occurred before "
            "these scenarios; it does not include tests added afterward.",
        ],
    }

    write_json(EVIDENCE / "operator_report.json", report)

    print("-" * 45)
    print(f"Scenario results: {passed_scenarios}/{len(scenarios)} passed")
    print(f"Pytest exit code: {completed.returncode}")
    print("Created: evidence/full_test_output.txt")
    print("Created: evidence/operator_report.json")

    return 0 if completed.returncode == 0 and passed_scenarios == len(scenarios) else 1


if __name__ == "__main__":
    raise SystemExit(main())
