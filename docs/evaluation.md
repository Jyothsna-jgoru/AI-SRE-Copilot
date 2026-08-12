# Evaluation methodology

The project separates quality measurement from ordinary application data so the agent cannot access the answer key.

## Golden set

- 50 deterministic incidents
- Five observable scenario families
- One hidden root-cause category and description per incident
- Required evidence-source prefixes per case
- More than 1,000 structured logs

## Metrics

1. Root-cause category accuracy compares the validated report with the hidden label.
2. Evidence coverage verifies that required evidence-source types were cited.
3. Structured-output validity measures Pydantic schema acceptance.
4. Unsupported-citation rate rejects evidence IDs absent from tool output.
5. Unsafe-action count detects claims that the application executed remediation.
6. Diagnosis latency measures the worker's actual start-to-completion duration.

## Reporting rule

No README, resume bullet, or demo page claims an accuracy or latency number until the complete local Ollama run produces it. Acceptance targets are not results.

## Load testing

`locust -f tests/locustfile.py --host http://localhost:8000`

The 20-RPS target applies to request intake and read APIs. It does not mean one CPU-hosted model can complete 20 diagnoses per second.

