"""Tests for the Decision dataclass."""

import pytest

from confgate import Decision


def make_decision(**overrides) -> Decision:
    defaults = dict(
        category="security",
        confidence=0.9,
        reasoning="SQL injection risk in query builder.",
    )
    return Decision(**{**defaults, **overrides})


class TestDecisionDefaults:
    def test_valid_creation_with_defaults(self):
        d = make_decision()
        assert d.category == "security"
        assert d.confidence == 0.9
        assert d.reasoning == "SQL injection risk in query builder."
        assert d.severity == "medium"
        assert d.line_ref is None
        assert d.abstained is False

    def test_all_fields_set_explicitly(self):
        d = Decision(
            category="style",
            confidence=0.6,
            reasoning="Missing type hint.",
            severity="low",
            line_ref="src/auth.py:42",
            abstained=False,
        )
        assert d.line_ref == "src/auth.py:42"
        assert d.severity == "low"


class TestDecisionValidation:
    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            make_decision(confidence=1.1)

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            make_decision(confidence=-0.01)

    def test_confidence_exactly_zero_is_valid(self):
        d = make_decision(confidence=0.0)
        assert d.confidence == 0.0

    def test_confidence_exactly_one_is_valid(self):
        d = make_decision(confidence=1.0)
        assert d.confidence == 1.0

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError, match="severity"):
            make_decision(severity="fatal")

    @pytest.mark.parametrize("sev", ["low", "medium", "high", "critical"])
    def test_all_valid_severities(self, sev):
        d = make_decision(severity=sev)
        assert d.severity == sev


class TestDecisionToDict:
    def test_to_dict_keys(self):
        d = make_decision()
        result = d.to_dict()
        assert set(result.keys()) == {
            "category", "confidence", "reasoning", "severity", "line_ref", "abstained"
        }

    def test_to_dict_values(self):
        d = Decision(
            category="security",
            confidence=0.85,
            reasoning="Hardcoded secret.",
            severity="high",
            line_ref="config.py:10",
            abstained=False,
        )
        assert d.to_dict() == {
            "category": "security",
            "confidence": 0.85,
            "reasoning": "Hardcoded secret.",
            "severity": "high",
            "line_ref": "config.py:10",
            "abstained": False,
        }

    def test_to_dict_line_ref_none(self):
        d = make_decision()
        assert d.to_dict()["line_ref"] is None

    def test_to_dict_reflects_abstained_state(self):
        d = make_decision()
        d.abstained = True
        assert d.to_dict()["abstained"] is True


class TestDecisionStr:
    def test_str_not_abstained(self):
        d = make_decision(severity="high", confidence=0.9)
        s = str(d)
        assert "[HIGH]" in s
        assert "0.90" in s
        assert "ABSTAINED" not in s

    def test_str_abstained(self):
        d = make_decision()
        d.abstained = True
        assert "ABSTAINED" in str(d)

    def test_str_includes_line_ref(self):
        d = make_decision(line_ref="src/auth.py:42")
        assert "src/auth.py:42" in str(d)

    def test_str_no_line_ref_omits_at(self):
        d = make_decision(line_ref=None)
        assert " @ " not in str(d)
