"""Layer 4.5: safety guards между Layer 3 decision и Layer 5 execution.

Файлы:
- ``halt_flag`` — emergency stop file flag (manual/drawdown/streak halt)

Hot path: только cheap checks (file existence, in-memory state).
Heavy work (DB queries) делается в guard threads / cron.
"""

from core.safety.halt_flag import (
    HaltFlag,
    HaltReason,
    make_consecutive_losses_halt,
    make_drawdown_halt,
    make_manual_halt,
)

__all__ = [
    "HaltFlag",
    "HaltReason",
    "make_consecutive_losses_halt",
    "make_drawdown_halt",
    "make_manual_halt",
]
