"""Game-title specific extraction strategies.

各 ``GameInterpreter`` 実装は内側 Session の DOM を walk し，title 固有の
タグ階層から ``RawTradedGoodTriple`` を yield する責務を持つ．
"""

from .anno117 import Anno117Interpreter
from .anno1800 import Anno1800Interpreter
from .base import (
    ExtractionContext,
    GameInterpreter,
    RawTradedGoodTriple,
    select_interpreter,
)

__all__ = [
    "Anno117Interpreter",
    "Anno1800Interpreter",
    "ExtractionContext",
    "GameInterpreter",
    "RawTradedGoodTriple",
    "select_interpreter",
]
