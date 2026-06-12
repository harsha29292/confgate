<div align="center">

<img src="https://raw.githubusercontent.com/harsha/confgate/main/assets/logo.png" alt="confgate" width="80" />

# confgate

**Confidence-gated decisions for LLM agent outputs.**

Agents abstain when they're not sure enough. Findings reach developers only when they should.

[![PyPI version](https://img.shields.io/pypi/v/confgate?color=1A56DB&labelColor=1E293B&style=flat-square)](https://pypi.org/project/confgate/)
[![Python](https://img.shields.io/pypi/pyversions/confgate?color=1A56DB&labelColor=1E293B&style=flat-square)](https://pypi.org/project/confgate/)
[![CI](https://img.shields.io/github/actions/workflow/status/harsha/confgate/ci.yml?color=166534&labelColor=1E293B&style=flat-square&label=CI)](https://github.com/harsha/confgate/actions)
[![License](https://img.shields.io/pypi/l/confgate?color=64748B&labelColor=1E293B&style=flat-square)](LICENSE)
[![Zero dependencies](https://img.shields.io/badge/dependencies-zero-7C3AED?labelColor=1E293B&style=flat-square)](#)

</div>

---

## The problem

LLM agents are noisy. A security agent that flags "possible SQL injection — confidence 0.4" wastes a developer's time more than it helps. Enough false positives and the tool gets disabled entirely.

This is **false positive fatigue** — and it's why most automated LLM-based review tools fail in practice.

## What confgate does

Wraps agent functions with a confidence threshold. Findings below the threshold come back with `abstained=True`. Findings above it pass through unchanged. The caller decides what to surface.

```python
from confgate import Decision, gate

@gate(threshold=0.75)
def security_agent(diff: str) -> Decision:
    # your LLM call here
    return Decision(
        category="security",
        confidence=0.5,           # below threshold
        reasoning="Possible SQL injection in query builder.",
        severity="high",
        line_ref="src/db.py:88",
    )

result = security_agent(diff)
print(result.abstained)   # True  — suppressed before it reaches a developer
print(result.confidence)  # 0.5   — still available for logging / monitoring
```

---

## Install

```bash
pip install confgate
```

Zero runtime dependencies. Pure Python 3.10+.

---

## Core concepts

### `Decision`

The structured output every agent returns.

```python
from dataclasses import dataclass

@dataclass
class Decision:
    category:   str         # 'security' | 'style' | 'logic' | anything you define
    confidence: float       # 0.0 – 1.0, provided by your LLM
    reasoning:  str         # one sentence, shown to the end user
    severity:   str         # 'low' | 'medium' | 'high' | 'critical'
    line_ref:   str | None  # optional — e.g. 'src/auth.py:42'
    abstained:  bool        # set by @gate, never by you
```

`Decision` validates itself on construction — `confidence` must be in `[0.0, 1.0]`, `severity` must be one of the four valid values.

### `@gate`

A decorator factory. Apply it to any agent function that returns a `Decision`.

```python
@gate(threshold=0.8)          # threshold validated at decoration time
def my_agent(diff: str) -> Decision:
    ...
```

- **Above threshold** — returned as-is, `abstained=False`
- **Below threshold** — returned with `abstained=True`
- **Equal to threshold** — passes. A threshold is a minimum bar, not a ceiling.
- **Wrong return type** — raises `InvalidDecisionError` immediately

---

## Real-world pattern: multi-agent PR reviewer

```python
from confgate import Decision, gate

@gate(threshold=0.75)
def security_agent(diff: str) -> Decision:
    raw = call_llm(SECURITY_PROMPT.format(diff=diff))
    data = parse_json(raw)
    return Decision(
        category="security",
        confidence=data["confidence"],
        reasoning=data["reasoning"],
        severity=data["severity"],
    )

@gate(threshold=0.75)
def style_agent(diff: str) -> Decision:
    raw = call_llm(STYLE_PROMPT.format(diff=diff))
    data = parse_json(raw)
    return Decision(
        category="style",
        confidence=data["confidence"],
        reasoning=data["reasoning"],
        severity=data["severity"],
    )

def orchestrate(diff: str) -> list[Decision]:
    agents = [security_agent, style_agent]
    results = [agent(diff) for agent in agents]
    
    # only surface what agents were confident about
    return [r for r in results if not r.abstained]
```

---

## Prompt pattern for LLM-generated confidence

Tell the model exactly what confidence scores mean — otherwise values are inconsistent across calls.

```python
SECURITY_PROMPT = """
You are a security code reviewer. Analyze the following git diff.

Respond ONLY with valid JSON. No markdown, no backticks.
{
  "has_finding": true | false,
  "confidence": 0.0-1.0,
  "reasoning": "one sentence explanation",
  "severity": "low" | "medium" | "high" | "critical"
}

Confidence guide:
- 0.9+   : obvious issue (hardcoded secret, SQL injection)
- 0.7-0.9: likely issue, some context needed
- 0.5-0.7: possible issue, uncertain
- below 0.5: not a real finding

DIFF:
{diff}
"""
```

---

## Serialisation

`to_dict()` returns a plain dict for JSON serialisation — useful for posting findings to GitHub review comments, logging, or monitoring.

```python
result.to_dict()
# {
#   "category": "security",
#   "confidence": 0.5,
#   "reasoning": "Possible SQL injection in query builder.",
#   "severity": "high",
#   "line_ref": "src/db.py:88",
#   "abstained": True
# }

str(result)
# [HIGH] [ABSTAINED] security @ src/db.py:88 (confidence=0.50): Possible SQL injection...
```

---

## Error handling

```python
from confgate import GateError, InvalidDecisionError

# Bad threshold — caught at decoration time
@gate(threshold=1.5)          # raises ValueError immediately
def agent(): ...

# Wrong return type — caught at call time  
@gate(threshold=0.75)
def bad_agent(diff: str) -> Decision:
    return {"confidence": 0.9}  # raises InvalidDecisionError on call

# Catch any confgate error
try:
    result = agent(diff)
except GateError as e:
    print(f"confgate error: {e}")
```

---

## API reference

### `gate(threshold: float = 0.8)`

| Parameter | Type | Default | Description |
|---|---|---|---|
| `threshold` | `float` | `0.8` | Minimum confidence to surface a finding. Must be `0.0 – 1.0`. |

Raises `ValueError` at decoration time if threshold is out of range.

### `Decision`

| Field | Type | Default | Description |
|---|---|---|---|
| `category` | `str` | required | Free-form finding type. You define the taxonomy. |
| `confidence` | `float` | required | LLM-generated confidence score. Must be `0.0 – 1.0`. |
| `reasoning` | `str` | required | One-sentence explanation shown to the end user. |
| `severity` | `str` | `"medium"` | One of `low`, `medium`, `high`, `critical`. |
| `line_ref` | `str \| None` | `None` | Optional code location, e.g. `src/auth.py:42`. |
| `abstained` | `bool` | `False` | Set by `@gate`. Never set this yourself. |

### Exceptions

| Exception | When |
|---|---|
| `GateError` | Base class for all confgate errors. |
| `InvalidDecisionError` | Decorated function returned a non-`Decision` value. |

---

## Design decisions

**Zero dependencies** — installs into any Python environment without version conflicts.

**Abstained findings are returned, not dropped** — the caller decides whether to log, discard, or escalate. confgate never makes that choice silently.

**No category validation** — `category` is a free-form string. confgate doesn't know your domain vocabulary and shouldn't.

**Strict less-than for threshold** — equal confidence passes. A threshold is a minimum bar.

**No async support in v0.1.0** — coming in v0.2.0. Handle concurrency at the orchestrator level with `asyncio.gather` for now.

---

## Development

```bash
git clone https://github.com/harsha/confgate
cd confgate
pip install -e ".[dev]"
pytest -v
```

CI runs on Python 3.10, 3.11, and 3.12 on every push and PR.

---

## Roadmap

- [ ] `@async_gate` — async support for coroutine agent functions
- [ ] `GateConfig` — shared config object across multiple agents
- [ ] Logprob-based confidence — derive confidence from token probabilities instead of prompting
- [ ] `Verdict` — aggregate multiple `Decision` objects into a single review summary

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built by [Harsha](https://github.com/harsha) · [PyPI](https://pypi.org/project/confgate/) · [Issues](https://github.com/harsha/confgate/issues)

</div>