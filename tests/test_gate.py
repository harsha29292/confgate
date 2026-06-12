"""Tests for the @gate decorator."""

import pytest

from confgate import Decision, InvalidDecisionError, gate


def _decision(confidence: float, **kwargs) -> Decision:
    return Decision(
        category="security",
        confidence=confidence,
        reasoning="Test finding.",
        **kwargs,
    )


class TestGateThreshold:
    def test_above_threshold_not_abstained(self):
        @gate(threshold=0.75)
        def agent() -> Decision:
            return _decision(0.9)

        result = agent()
        assert result.abstained is False

    def test_below_threshold_abstained(self):
        @gate(threshold=0.75)
        def agent() -> Decision:
            return _decision(0.5)

        result = agent()
        assert result.abstained is True

    def test_exactly_at_threshold_not_abstained(self):
        """Equal to threshold must pass — strictly less-than triggers abstain."""
        @gate(threshold=0.75)
        def agent() -> Decision:
            return _decision(0.75)

        result = agent()
        assert result.abstained is False

    def test_just_below_threshold_abstained(self):
        @gate(threshold=0.75)
        def agent() -> Decision:
            return _decision(0.7499)

        result = agent()
        assert result.abstained is True

    def test_default_threshold_is_0_8(self):
        @gate()
        def agent() -> Decision:
            return _decision(0.79)

        result = agent()
        assert result.abstained is True

    def test_default_threshold_passes_0_8(self):
        @gate()
        def agent() -> Decision:
            return _decision(0.8)

        result = agent()
        assert result.abstained is False


class TestGateMetadataPreservation:
    def test_preserves_name(self):
        @gate(threshold=0.5)
        def my_agent() -> Decision:
            """Agent docstring."""
            return _decision(0.9)

        assert my_agent.__name__ == "my_agent"

    def test_preserves_doc(self):
        @gate(threshold=0.5)
        def my_agent() -> Decision:
            """Agent docstring."""
            return _decision(0.9)

        assert my_agent.__doc__ == "Agent docstring."

    def test_preserves_annotations(self):
        @gate(threshold=0.5)
        def my_agent(diff: str) -> Decision:
            return _decision(0.9)

        assert my_agent.__annotations__["diff"] is str


class TestGateReturnTypeEnforcement:
    def test_non_decision_return_raises(self):
        @gate(threshold=0.5)
        def bad_agent():
            return {"confidence": 0.9}

        with pytest.raises(InvalidDecisionError):
            bad_agent()

    def test_none_return_raises(self):
        @gate(threshold=0.5)
        def bad_agent():
            return None

        with pytest.raises(InvalidDecisionError):
            bad_agent()

    def test_string_return_raises(self):
        @gate(threshold=0.5)
        def bad_agent():
            return "finding"

        with pytest.raises(InvalidDecisionError):
            bad_agent()


class TestGateThresholdValidation:
    def test_threshold_above_one_raises_at_decoration(self):
        with pytest.raises(ValueError, match="threshold"):
            @gate(threshold=1.1)
            def agent():
                pass

    def test_threshold_below_zero_raises_at_decoration(self):
        with pytest.raises(ValueError, match="threshold"):
            @gate(threshold=-0.1)
            def agent():
                pass

    def test_threshold_exactly_zero_is_valid(self):
        @gate(threshold=0.0)
        def agent() -> Decision:
            return _decision(0.0)

        result = agent()
        assert result.abstained is False

    def test_threshold_exactly_one_is_valid(self):
        @gate(threshold=1.0)
        def agent() -> Decision:
            return _decision(0.99)

        result = agent()
        assert result.abstained is True


class TestGatePassesArguments:
    def test_wrapped_function_receives_args(self):
        received = {}

        @gate(threshold=0.5)
        def agent(diff: str, extra: int = 0) -> Decision:
            received["diff"] = diff
            received["extra"] = extra
            return _decision(0.9)

        agent("some diff", extra=7)
        assert received == {"diff": "some diff", "extra": 7}
