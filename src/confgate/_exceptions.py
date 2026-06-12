"""Exceptions raised by confgate."""


class GateError(Exception):
    """Base exception for all confgate errors."""


class InvalidDecisionError(GateError):
    """Raised when a @gate-decorated function returns a non-Decision value."""
