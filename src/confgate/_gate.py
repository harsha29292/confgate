"""@gate decorator — confidence-gates a function that returns a Decision."""

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from confgate._core import Decision
from confgate._exceptions import InvalidDecisionError

F = TypeVar("F", bound=Callable[..., Decision])


def gate(threshold: float = 0.8) -> Callable[[F], F]:
    """Decorator factory that abstains low-confidence decisions.

    Args:
        threshold: Minimum confidence required to pass. Decisions with
                   confidence strictly below this value have abstained=True.
                   Must be between 0.0 and 1.0 inclusive.

    Raises:
        ValueError: At decoration time if threshold is outside [0.0, 1.0].
        InvalidDecisionError: At call time if the wrapped function does not
                              return a Decision instance.
    """
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
