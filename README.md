# Topic 5 — Validation in Code

**Tayana Activities | Tool Calling Engineering**  

## Overview

This project demonstrates a validation gateway for tool-calling workflows. Requests are checked against typed contracts and input schemas, evaluated against business rules, and gated by evidence, authorization, and approval checks before protected handlers execute.

The implementation uses a fake provider and sample order records. It does not issue real refunds or connect to a payment system.

## Assessment tasks

1. **Tool contract and registry:** typed request/result contracts, status and next-action enums, versioned tool specifications, and registry lookup.
2. **Central validation pipeline:** schema validation, business-rule checks, verified-evidence requirement, and approval gate.
3. **Security and failure handling:** registered-tool/version checks, role authorization, validation rejection, and safe provider error responses.
4. **Reliability and observability:** structured JSON audit events, in-process rate limiting, and request-ID idempotency.
5. **Evidence and operator report:** generated JSON input schemas, test output, gateway scenario traces, and an operator report.

## Architecture

```text
ToolCall
   |
   v
ToolRegistry ---- unknown tool/version ---> NOT_FOUND
   |
   v
Role authorization ---- denied -----------> DENIED
   |
   v
Rate limiter ---------- limited -----------> RATE_LIMITED
   |
   v
ValidationPipeline
   |-- schema validation
   |-- business rules
   |-- evidence check
   |-- approval check
   |
   v
Registered handler
   |
   v
ToolResult + structured audit event
```

## Project structure

```text
Validation_in_Code_Assessment/
├── src/
│   ├── __init__.py
│   ├── contracts.py
│   ├── registry.py
│   ├── schemas.py
│   ├── validation.py
│   ├── providers.py
│   ├── gateway.py
│   ├── reliability.py
│   └── observability.py
├── tests/
├── schemas/
│   ├── order_lookup_input.json
│   └── refund_request_input.json
├── traces/
├── evidence/
├── generate_schemas.py
├── generate_evidence.py
├── requirements.txt
└── .gitignore
```

## Requirements

- Python 3.13.9 (used during the assessment)
- `pydantic==2.14.1`
- `pytest==9.1.1`
- `httpx==0.28.1`

## Setup on Windows CMD

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## Run tests

```bat
python -m pytest -q
```

The recorded full-suite run reported:

```text
53 passed in 0.30s
```

Individual test groups:

```bat
python -m pytest tests\test_task1_contract_registry.py -q
python -m pytest tests\test_task2_validation.py -q
python -m pytest tests\test_task3_security_failures.py -q
python -m pytest tests\test_task4_reliability.py -q
python -m pytest tests\test_task4_gateway_reliability.py -q
```

## Generate schemas and evidence

```bat
python generate_schemas.py
python generate_evidence.py
python -m json.tool evidence\operator_report.json
type evidence\full_test_output.txt
```

Review the report after generation. The generator executes local gateway scenarios using the fake provider; these are local executions, not production transactions. Regenerate evidence after code or test changes so the saved test output matches the final project state.

## Example behavior

- Valid order lookup: `ok`
- Invalid input: `invalid`
- Unauthorized role: `denied`
- Refund missing approval: `needs_approval`
- Rate-limited request: `rate_limited`
- Approved simulated refund request: `ok`, with `submitted_for_review`

## Security and limitations

- **Fake provider:** no real order system or payment/refund service is connected.
- **Trust boundary:** role, evidence, and approval values are accepted as gateway function arguments in this educational implementation. Production systems must derive them from authenticated identity, trusted evidence verification, and a separate approval service.
- **Process-local reliability:** rate limiting, idempotency storage, and execution coordination are in memory and do not coordinate across multiple processes or hosts.
- **Idempotency:** production implementations should bind keys to canonical request hashes, detect reuse with different payloads, persist results, and define recovery behavior for ambiguous provider timeouts.
- **Observability:** structured logs omit raw arguments, but production deployments also need access controls, retention policy, monitoring, and redaction review.

## Reflection (approximately 300 words)

This project helped me understand that tool calling needs more than a well-formed JSON object. A request can be syntactically valid and still be unsafe, unauthorized, unsupported by business rules, or incomplete because required evidence or approval is missing. Separating the validation pipeline from tool execution made these decisions easier to reason about and test.

The typed contracts and versioned registry establish a clear interface between the caller and available tools. Pydantic schemas reject malformed inputs and unexpected fields, while the business-rule stage checks the order record and refund amount. Evidence and approval checks are separate stages, which makes the reason for rejecting or pausing a request explicit. The gateway then applies role checks and rate limiting before invoking a handler.

Testing was especially useful because it verifies not only the response status but also whether a protected side effect occurred. For example, invalid, unauthorized, unapproved, and rate-limited refund requests should not create simulated refund records. The idempotency tests demonstrate how a repeated request ID can reuse a stored result rather than repeat a completed action. Structured audit events also make the request path easier to inspect without logging raw customer arguments.

The project is an educational prototype, not a production refund system. Its fake provider prevents real financial actions, and its reliability stores operate only in the current process. A production design would need authenticated identities, independently verified evidence, a trusted approval workflow, durable idempotency storage, cross-worker coordination, and careful recovery for provider timeouts where the outcome is uncertain.

Overall, the activity reinforced a useful engineering principle: validate at multiple layers, keep authorization and approval separate from input validation, and test that rejected requests do not cause side effects. The next improvement would be to add request-hash conflict detection and persistent idempotency records, then test the gateway under concurrent requests and simulated provider failures.
