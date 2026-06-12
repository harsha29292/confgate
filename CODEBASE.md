# confgate — End-to-End Codebase Guide

> A complete walkthrough of every file in the project: what it does, how it fits together, and why each design decision was made.

---

## Table of Contents

1. [What the package does](#1-what-the-package-does)
2. [Repository layout](#2-repository-layout)
3. [How the pieces connect — data flow](#3-how-the-pieces-connect--data-flow)
4. [src/confgate/_exceptions.py](#4-srcconfgate_exceptionspy)
5. [src/confgate/_core.py](#5-srcconfgate_corepy)
6. [src/confgate/_gate.py](#6-srcconfgate_gatepy)
7. [src/confgate/__init__.py](#7-srcconfgate__init__py)
8. [tests/test_decision.py](#8-teststest_decisionpy)
9. [tests/test_gate.py](#9-teststest_gatepy)
10. [pyproject.toml](#10-pyprojecttoml)
11. [.github/workflows/ci.yml](#11-githubworkflowsciyml)
12. [End-to-end trace: one agent call](#12-end-to-end-trace-one-agent-call)
13. [Design constraints and why they exist](#13-design-constraints-and-why-they-exist)

---

## 1. What the package does

LLM-based agents are noisy. When a security agent scans a diff and reports "possible SQL injection — confidence 0.4", that report is more likely to waste a reviewer's time than to catch a real bug. **confgate** solves this by letting the agent declare its own confidence, and automatically suppressing findings that fall below a caller-defined threshold.

The core idea in one sentence: *wrap an agent function with `@gate(threshold=0.75)` and it will return a `Decision` whose `abstained` flag tells callers whether to trust the finding.*

The two exported primitives are:

- **`Decision`** — a dataclass carrying a finding's category, confidence, reasoning, severity, and optional code location.
- **`gate`** — a decorator factory that inspects the returned `Decision` and sets `abstained=True` when confidence is below the threshold.

---

## 2. Repository layout

```
confgate/
│
├── pyproject.toml                  # build config, metadata, dev deps
├── README.md                       # public-facing quick-start
├── LICENSE                         # MIT
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions: pytest on 3.10 / 3.11 / 3.12
│
├── tests/
│   ├── __init__.py                 # marks tests/ as a package
│   ├── test_decision.py            # 19 tests covering Decision
│   └── test_gate.py                # 17 tests covering @gate
│
└── src/
    └── confgate/                   # the installable package
        ├── __init__.py             # public API surface
        ├── _core.py                # Decision dataclass
        ├── _gate.py                # @gate decorator factory
        └── _exceptions.py         # GateError, InvalidDecisionError
```

The `src/` layout is deliberate: it prevents Python from accidentally importing the local source directory as though it were an installed package during test runs. `pip install -e .` installs the package properly, and the test runner always imports from the installed copy.

---

## 3. How the pieces connect — data flow

```
caller code
    │
    │  @gate(threshold=0.75)          ← _gate.py validates threshold at import time
    │  def my_agent(diff: str) -> Decision:
    │      ...
    │      return Decision(...)       ← _core.py validates confidence + severity
    │
    ▼
gate wrapper (inside _gate.py)
    │
    ├── calls my_agent(diff)
    │       └── returns Decision instance
    │
    ├── isinstance check             ← raises InvalidDecisionError (_exceptions.py)
    │       if not a Decision
    │
    ├── confidence < threshold?
    │       yes → result.abstained = True
    │       no  → result.abstained stays False
    │
    └── returns result to caller
            │
            ▼
        caller checks result.abstained
            False → use the finding
            True  → discard / log / ignore
```

The three internal modules form a strict dependency chain with no cycles:

```
_exceptions.py   (no internal imports)
      ↑
_core.py         (no internal imports)
      ↑
_gate.py         (imports Decision from _core, InvalidDecisionError from _exceptions)
      ↑
__init__.py      (re-exports all three)
```

---

## 4. `src/confgate/_exceptions.py`

```python
"""Exceptions raised by confgate."""


class GateError(Exception):
    """Base exception for all confgate errors."""


class InvalidDecisionError(GateError):
    """Raised when a @gate-decorated function returns a non-Decision value."""
```

**What it does**

Defines the exception hierarchy. There are exactly two classes:

- `GateError` — the base. Callers who want to catch any confgate error catch this.
- `InvalidDecisionError` — a subclass raised specifically when the wrapped function returns something that is not a `Decision` instance.

**Why it lives in its own file**

`_gate.py` needs `InvalidDecisionError`. `_core.py` does not. Keeping exceptions in a separate module breaks what would otherwise be a circular import: if `_core.py` defined exceptions, `_gate.py` would import `_core.py` both for `Decision` and for the exception class, which works but conflates two concerns. Separate module, no ambiguity.

**Why the hierarchy matters**

Downstream code that builds on confgate can do either of:

```python
except GateError:           # catch any confgate failure
except InvalidDecisionError: # catch only the contract-violation case
```

Both are valid. A single flat exception class would remove that choice.

---

## 5. `src/confgate/_core.py`

```python
"""Decision dataclass — the core data structure for confgate."""

from dataclasses import dataclass, field

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


@dataclass
class Decision:
    """A structured finding produced by an LLM agent."""

    category: str
    confidence: floatjnk

    
    reasoning: str
    severity: str = "medium"
    line_ref: str | None = None
    abstained: bool = False

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of {sorted(_VALID_SEVERITIES)}, got {self.severity!r}"
            )

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialisation."""
        return {
            "category": self.category,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "severity": self.severity,
            "line_ref": self.line_ref,
            "abstained": self.abstained,
        }

    def __str__(self) -> str:
        abstained_tag = " [ABSTAINED]" if self.abstained else ""
        loc = f" @ {self.line_ref}" if self.line_ref else ""
        return (
            f"[{self.severity.upper()}]{abstained_tag} {self.category}{loc}"
            f" (confidence={self.confidence:.2f}): {self.reasoning}"
        )
```

### Fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `category` | `str` | required | What kind of finding: `"security"`, `"style"`, `"performance"`, etc. No validation — the caller owns this vocabulary. |
| `confidence` | `float` | required | Agent's self-reported certainty, 0.0–1.0. Validated in `__post_init__`. |
| `reasoning` | `str` | required | One human-readable sentence shown to end users explaining the finding. |
| `severity` | `str` | `"medium"` | Impact label. Must be one of `"low"`, `"medium"`, `"high"`, `"critical"`. |
| `line_ref` | `str | None` | `None` | Optional code pointer, e.g. `"src/auth.py:42"`. Free-form string — confgate does not parse it. |
| `abstained` | `bool` | `False` | Never set by user code. Set to `True` by `@gate` when confidence falls below the threshold. |

### `__post_init__`

`@dataclass` calls `__post_init__` immediately after `__init__`. This is where validation runs:

- **Confidence range** — `0.0 <= confidence <= 1.0`. Both endpoints are valid (an agent can be completely uncertain or completely certain).
- **Severity vocabulary** — membership check against `_VALID_SEVERITIES`. A module-level set is used instead of a local one so the check is O(1) regardless of how many valid values there are.

Both validations raise `ValueError`, not a custom exception. `ValueError` is the Python convention for "this argument's value is wrong" and does not require the caller to import a custom type to catch it.

### `to_dict()`

Returns a plain `dict` with all six fields. The primary use case is serialising findings to JSON for GitHub PR review comments or API responses:

```python
import json
comment_body = json.dumps(result.to_dict())
```

The method is explicit — it lists every key — rather than using `dataclasses.asdict()`. This means adding a future internal field to the dataclass will not silently appear in serialised output until `to_dict()` is updated.

### `__str__`

Produces a single-line human summary, for example:

```
[HIGH] security @ src/auth.py:42 (confidence=0.91): Hardcoded API key detected.
[MEDIUM] [ABSTAINED] style (confidence=0.42): Missing return type annotation.
```

The `[ABSTAINED]` tag appears between the severity bracket and the category when `abstained=True`. The confidence is formatted with two decimal places (`.2f`) so output columns align in logs.

---

## 6. `src/confgate/_gate.py`

```python
"""@gate decorator — confidence-gates a function that returns a Decision."""

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from confgate._core import Decision
from confgate._exceptions import InvalidDecisionError

F = TypeVar("F", bound=Callable[..., Decision])


def gate(threshold: float = 0.8) -> Callable[[F], F]:
    """Decorator factory that abstains low-confidence decisions."""
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(
            f"gate threshold must be between 0.0 and 1.0, got {threshold}"
        )

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if not isinstance(result, Decision):
                raise InvalidDecisionError(
                    f"{fn.__name__} must return a Decision instance, "
                    f"got {type(result).__name__}"
                )
            if result.confidence < threshold:
                result.abstained = True
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
```

### The three-layer function structure

`gate` is a *decorator factory* — calling it produces a decorator, not a decorated function. There are three nested functions:

```
gate(threshold)           ← layer 1: validates threshold, captures it in closure
  └── decorator(fn)       ← layer 2: receives the function being decorated
        └── wrapper(...)  ← layer 3: runs on every call to the decorated function
```

This structure is required because `@gate(threshold=0.75)` has parentheses — it calls `gate` first and applies the returned `decorator` to the function. Compare to a no-argument decorator like `@staticmethod` which does not have this extra layer.

### Threshold validation at decoration time

```python
if not (0.0 <= threshold <= 1.0):
    raise ValueError(...)
```

This check runs at *module load time* when Python processes the `@gate(threshold=1.1)` line — not at the first function call. The advantage: a bad threshold is caught immediately when the code is imported, not silently at runtime when an agent finally executes.

### `@wraps(fn)`

```python
@wraps(fn)
def wrapper(*args, **kwargs):
```

`functools.wraps` copies `__name__`, `__qualname__`, `__doc__`, `__annotations__`, and `__module__` from `fn` onto `wrapper`. Without it:

```python
my_agent.__name__  # would be "wrapper", not "my_agent"
my_agent.__doc__   # would be None
```

This matters for debugging, logging frameworks, and any introspection tool that looks at function metadata.

### Type variable `F`

```python
F = TypeVar("F", bound=Callable[..., Decision])
```

`F` lets the type checker understand that `decorator` returns the *same callable type* it received. Without it, a type checker would see `gate` as returning `Callable[..., Decision]` — losing parameter information. With `F`, the checker knows that `my_agent`'s parameter signature is preserved through decoration.

### The isinstance check

```python
if not isinstance(result, Decision):
    raise InvalidDecisionError(...)
```

This enforces the contract: a `@gate`-decorated function must return a `Decision`. Python does not enforce return type annotations at runtime, so without this check a function that accidentally returns `None` or a dict would pass silently — only the `result.abstained` access later would raise an `AttributeError` with a confusing message. The explicit check produces a clear, actionable error naming both the function and the type it returned.

### The abstain logic

```python
if result.confidence < threshold:
    result.abstained = True
return result
```

Three things to note:

1. **Strictly less than** — `confidence == threshold` passes. Equal confidence meets the bar.
2. **Mutation, not a copy** — `result.abstained` is set on the same object the wrapped function created. The caller receives the identical object, so `id(result)` is the same before and after.
3. **Always returns** — the Decision is returned whether it abstained or not. The caller decides what to do with it; confgate never silently drops findings.

---

## 7. `src/confgate/__init__.py`

```python
"""confgate — confidence-gated decisions for LLM agent outputs."""

from confgate._core import Decision
from confgate._exceptions import GateError, InvalidDecisionError
from confgate._gate import gate

__version__ = "0.1.0"
__all__ = ["Decision", "gate", "GateError", "InvalidDecisionError"]
```

**What it does**

This is the only file users ever import from. It re-exports the four public names and defines `__version__`.

**Why `__all__`**

`__all__` controls what `from confgate import *` exposes, and also communicates intent to documentation generators and IDEs: these four names are the stable public API. Internal names prefixed with `_` (like `_core`, `_gate`, `_exceptions`) are excluded automatically and are subject to change without notice.

**Why internal modules use `_` prefixes**

The underscore prefix is Python's convention for "not public". Users should never need to `from confgate._core import Decision` — they always go through `confgate` directly. The prefix also signals that the internal module structure can be refactored freely without it being a breaking change.

---

## 8. `tests/test_decision.py`

### Test helper: `make_decision`

```python
def make_decision(**overrides) -> Decision:
    defaults = dict(
        category="security",
        confidence=0.9,
        reasoning="SQL injection risk in query builder.",
    )
    return Decision(**{**defaults, **overrides})
```

A factory function that provides sensible defaults for every required field so individual tests only specify the field they care about:

```python
make_decision(confidence=1.1)   # only change confidence
make_decision(severity="fatal") # only change severity
```

This keeps tests short and focused on one variable at a time.

### `TestDecisionDefaults` (2 tests)

Verifies that a valid Decision can be constructed and that all defaults are applied correctly:
- `severity` defaults to `"medium"`
- `line_ref` defaults to `None`
- `abstained` defaults to `False`

### `TestDecisionValidation` (6 tests)

Covers the `__post_init__` guard clauses:

| Test | What it verifies |
|---|---|
| `test_confidence_above_one_raises` | `confidence=1.1` raises `ValueError` |
| `test_confidence_below_zero_raises` | `confidence=-0.01` raises `ValueError` |
| `test_confidence_exactly_zero_is_valid` | `0.0` is a valid boundary value |
| `test_confidence_exactly_one_is_valid` | `1.0` is a valid boundary value |
| `test_invalid_severity_raises` | `severity="fatal"` raises `ValueError` |
| `test_all_valid_severities` | parametrised over all four valid values |

The boundary tests (`exactly_zero`, `exactly_one`) are important: they guard against an accidental strict inequality (`< 0.0` instead of `<= 0.0`) that would silently reject valid inputs.

### `TestDecisionToDict` (4 tests)

Verifies the serialisation path:
- Correct key set
- Correct values round-trip
- `line_ref=None` serialises to `None` (not absent)
- `abstained` reflects state at the time `to_dict()` is called, not at construction time

### `TestDecisionStr` (4 tests)

Verifies the human-readable format:
- Severity in uppercase brackets: `[HIGH]`
- `[ABSTAINED]` only present when `abstained=True`
- `line_ref` appears in output when set
- ` @ ` separator absent when `line_ref=None`

---

## 9. `tests/test_gate.py`

### Test helper: `_decision`

```python
def _decision(confidence: float, **kwargs) -> Decision:
    return Decision(
        category="security",
        confidence=confidence,
        reasoning="Test finding.",
        **kwargs,
    )
```

Parallel to `make_decision` in `test_decision.py` but parameterised primarily on `confidence`, which is the variable most tests need to control.

### `TestGateThreshold` (6 tests)

The core behaviour contract:

| Test | What it pins down |
|---|---|
| `test_above_threshold_not_abstained` | confidence 0.9, threshold 0.75 → passes |
| `test_below_threshold_abstained` | confidence 0.5, threshold 0.75 → abstains |
| `test_exactly_at_threshold_not_abstained` | confidence == threshold → passes (not strictly less-than) |
| `test_just_below_threshold_abstained` | confidence 0.7499, threshold 0.75 → abstains |
| `test_default_threshold_is_0_8` | `@gate()` with confidence 0.79 abstains |
| `test_default_threshold_passes_0_8` | `@gate()` with confidence 0.80 passes |

The `exactly_at_threshold` test is particularly important — it documents the `<` vs `<=` choice. If someone changes the comparison to `<=`, this test catches it immediately.

### `TestGateMetadataPreservation` (3 tests)

Verifies `@wraps` is working:

- `__name__` is `"my_agent"`, not `"wrapper"`
- `__doc__` is the original docstring, not `None`
- `__annotations__` contains the original type hints

Without these tests, someone could accidentally remove `@wraps` during a refactor and break every logging and debugging tool that reads function metadata.

### `TestGateReturnTypeEnforcement` (3 tests)

Verifies the `isinstance` check:
- Returning a `dict` raises `InvalidDecisionError`
- Returning `None` raises `InvalidDecisionError`
- Returning a `str` raises `InvalidDecisionError`

### `TestGateThresholdValidation` (4 tests)

Verifies that invalid thresholds are caught at decoration time, not call time:

```python
with pytest.raises(ValueError, match="threshold"):
    @gate(threshold=1.1)   # raises HERE, not when agent() is called
    def agent():
        pass
```

Also verifies the boundary values `0.0` and `1.0` are accepted.

### `TestGatePassesArguments` (1 test)

Verifies that `wrapper(*args, **kwargs)` correctly forwards all arguments to the wrapped function. This is easy to break if someone accidentally hardcodes `fn()` instead of `fn(*args, **kwargs)`.

---

## 10. `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "confgate"
version = "0.1.0"
description = "Confidence-gated decisions for LLM agent outputs"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
authors = [{ name = "Harsha" }]
keywords = ["agents", "llm", "confidence", "ai", "agentic"]
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Topic :: Software Development :: Libraries",
]
dependencies = []

[project.optional-dependencies]
dev = ["pytest", "pytest-cov"]

[tool.setuptools.packages.find]
where = ["src"]
```

### Key decisions

**`build-backend = "setuptools.build_meta"`**
The original spec listed `setuptools.backends.legacy:build`, which is only available in setuptools ≥ 69.3. Using the stable `setuptools.build_meta` backend ensures the build works on the full 3.10/3.11/3.12 matrix where older setuptools may be installed.

**`dependencies = []`**
Zero runtime dependencies is a hard constraint. Users can install confgate into any Python environment without pulling in numpy, pydantic, or anything else. The `dev` extra adds pytest only for development.

**`requires-python = ">=3.10"`**
The `str | None` union syntax in `_core.py` requires Python 3.10 (PEP 604). Using `Optional[str]` would allow 3.9 but the explicit union syntax is cleaner and 3.10 is already two major versions behind.

**`[tool.setuptools.packages.find] where = ["src"]`**
Tells setuptools to look for packages under `src/` rather than the project root. This is required by the `src/` layout — without it setuptools would not find `confgate` at all.

**`version` is hardcoded**
For v0.1.0 a hardcoded version in both `pyproject.toml` and `__init__.py` is the simplest approach. Before publishing to PyPI both places need to be updated in sync. A future improvement would be `setuptools-scm` to derive the version from git tags, eliminating duplication.

---

## 11. `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install package and dev dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: pytest --cov=confgate -v
```

### What triggers it

- Every push to `main`
- Every pull request (to any branch)

### Matrix strategy

GitHub runs three parallel jobs, one per Python version. All three must pass for a PR to be considered green. This guards against version-specific regressions — for example, a syntax that works in 3.12 but is a `SyntaxError` in 3.10.

### Install step

`pip install -e ".[dev]"` does two things:

1. Installs confgate itself in *editable* mode (`-e`), meaning Python imports directly from the `src/` directory without a build step. Changes to source files take effect without reinstalling.
2. Installs the `dev` optional-dependency group: `pytest` and `pytest-cov`.

### Test step

`pytest --cov=confgate -v` runs all tests and collects line coverage for the `confgate` package. The `-v` flag prints each test name individually so failures are easy to locate in the CI log.

---

## 12. End-to-end trace: one agent call

Here is the complete execution path for this code:

```python
from confgate import Decision, gate

@gate(threshold=0.75)
def security_agent(diff: str) -> Decision:
    """Detects security issues in a git diff."""
    return Decision(
        category="security",
        confidence=0.5,
        reasoning="Possible SQL injection in query builder.",
        severity="high",
        line_ref="src/db.py:88",
    )

result = security_agent("- query = 'SELECT * FROM users WHERE id=' + user_id")
print(result.abstained)  # True
print(result)
```

**Step 1 — module import**
`from confgate import Decision, gate` triggers `__init__.py`, which imports `Decision` from `_core`, `gate` from `_gate`, and the exceptions from `_exceptions`.

**Step 2 — decoration: `@gate(threshold=0.75)`**
Python calls `gate(threshold=0.75)`. Inside `gate`:
- `0.0 <= 0.75 <= 1.0` is `True` → no `ValueError`
- `decorator` is created as a closure capturing `threshold=0.75`
- `gate` returns `decorator`

Python immediately applies `decorator` to `security_agent`:
- `@wraps(security_agent)` copies `__name__`, `__doc__`, `__annotations__` onto `wrapper`
- `decorator` returns `wrapper`
- The name `security_agent` now refers to `wrapper`, but `wrapper.__name__ == "security_agent"`

**Step 3 — call: `security_agent("...")`**
`wrapper("- query = ...")` executes:
1. `fn("- query = ...")` calls the original `security_agent` function body
2. Inside the body, `Decision(category="security", confidence=0.5, ...)` is constructed
3. `Decision.__post_init__` runs: `0.0 <= 0.5 <= 1.0` ✓, `"high"` in `_VALID_SEVERITIES` ✓
4. The `Decision` object is returned to `wrapper` as `result`

**Step 4 — gate check**
Back in `wrapper`:
- `isinstance(result, Decision)` → `True` → no `InvalidDecisionError`
- `result.confidence < threshold` → `0.5 < 0.75` → `True`
- `result.abstained = True` — the field is mutated on the existing object

**Step 5 — return**
`wrapper` returns `result` to the caller. The caller receives the same `Decision` object with `abstained=True`.

**Step 6 — caller logic**
```python
result.abstained   # True
str(result)        # "[HIGH] [ABSTAINED] security @ src/db.py:88 (confidence=0.50): Possible SQL injection..."
result.to_dict()   # {"category": "security", "confidence": 0.5, ..., "abstained": True}
```

The caller can now filter, log, or discard the finding based on `result.abstained`.

---

## 13. Design constraints and why they exist

### Zero runtime dependencies

`dependencies = []` in `pyproject.toml` and no non-stdlib import in any source file. This means confgate can be installed into any Python environment — a minimal Lambda container, a locked corporate environment, a security-hardened CI image — without pulling in a dependency tree. It also means no version conflicts with pydantic, attrs, or any other library the user's project already uses.

### `src/` layout

Placing the package under `src/confgate/` rather than `confgate/` at the root prevents a subtle class of bugs where `import confgate` resolves to the local directory rather than the installed package. With `src/` layout, there is nothing named `confgate` at the root, so Python is forced to use the installed copy.

### Abstained decisions are returned, not dropped

`@gate` always returns the `Decision`. It never returns `None` or raises an exception for a low-confidence finding. This is intentional: the caller must decide whether to show, log, suppress, or escalate an abstained finding. Dropping it silently inside the library removes that choice.

### No category validation

`category` is a free-form string. `gate` does not check whether `"security"` or `"my_custom_type"` is in some list. Validating categories would require confgate to know about its callers' domain vocabulary, coupling the library to specific use cases. The caller owns the taxonomy.

### No async support in v0.1.0

The `wrapper` function uses `fn(*args, **kwargs)` without `await`. Adding `async def wrapper` and `await fn(...)` would require detecting whether `fn` is a coroutine function and branching, or providing a separate `@async_gate` decorator. That complexity is deferred to a future version when there is a concrete use case for it.

### `confidence < threshold` (strict less-than)

Equal confidence passes. If you set `threshold=0.75` and the agent returns `confidence=0.75`, the finding is surfaced. The intuition: a threshold is a minimum bar, and meeting the bar is sufficient. Changing this to `<=` would mean `threshold=1.0` is the only threshold where any finding passes, which would be surprising.

### `ValueError` for validation, not custom exceptions

`Decision.__post_init__` raises `ValueError`, not `InvalidDecisionError` or a new custom type. `ValueError` is the established Python convention for invalid argument values and does not require callers to import a special type to handle it. `GateError` and `InvalidDecisionError` exist only for confgate-specific contract violations (wrong return type from a decorated function) that have no standard exception analogue.
