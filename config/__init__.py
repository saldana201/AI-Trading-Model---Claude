"""Phase 12 — unified, layered, glass-box configuration.

    from config import get_config, get, update_config
    get("risk", "min_score")            # -> 6.0
    update_config({"risk": {"min_score": 7.0}})

Precedence: DEFAULTS < legacy env vars < confluence.json < runtime updates.
"""

from .schema import DEFAULTS, validate, deep_merge          # noqa: F401
from .loader import (get_config, get, update_config,        # noqa: F401
                     reset_cache, config_path, load)
from .presets import PRESETS, list_presets, get_preset      # noqa: F401
