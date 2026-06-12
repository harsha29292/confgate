"""confgate — confidence-gated decisions for LLM agent outputs."""

from confgate._core import Decision
from confgate._exceptions import GateError, InvalidDecisionError
from confgate._gate import gate

__version__ = "0.1.1"
__all__ = ["Decision", "gate", "GateError", "InvalidDecisionError"]
