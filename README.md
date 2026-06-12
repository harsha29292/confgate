# confgate

Confidence-gated decisions for LLM agent outputs.

> Prevent false-positive fatigue by abstaining from low-confidence findings.

## Installation

```bash
pip install confgate
```

## Quick start

```python
from confgate import Decision, gate

@gate(threshold=0.75)
def security_agent(diff: str) -> Decision:
    # your LLM call here
    return Decision(
        category="security",
        confidence=0.9,
        reasoning="Potential SQL injection in query builder.",
        severity="high",
        line_ref="src/db.py:42",
    )

result = security_agent(diff)
if not result.abstained:
    print(result)
```

## License

MIT
