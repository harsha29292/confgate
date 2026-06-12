"""Decision dataclass — the core data structure for confgate."""

from dataclasses import dataclass, field

_VALID_SEVERITIES = {"low", "medium", "high", "critical"}


@dataclass
class Decision:
    """A structured finding produced by an LLM agent.

    Attributes:
        category:   Type of finding, e.g. 'security' or 'style'.
        confidence: Agent's self-reported confidence, 0.0–1.0.
        reasoning:  One-sentence explanation shown to end users.
        severity:   Impact level — 'low', 'medium', 'high', or 'critical'.
        line_ref:   Optional code location, e.g. 'src/auth.py:42'.
        abstained:  Set True by @gate when confidence < threshold.
    """

    category: str
    confidence: float
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
