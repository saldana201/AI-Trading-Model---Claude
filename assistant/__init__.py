"""Phase 12 — trade assistant: sizing, plans, and live advice.

Everything traces: prices from engine-validated setups, quantities from
declared sizing formulas, actions from the lifecycle contract.
"""

from .sizing import size_position          # noqa: F401
from .plan import build_plan               # noqa: F401
from .advisor import advise, record_fill   # noqa: F401
