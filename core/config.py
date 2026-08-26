"""
Harmonic Pattern Configuration & Fibonacci Ratio Definitions.
Defines all 6 XABCD harmonic patterns with their exact Fibonacci DNA.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
import numpy as np


@dataclass
class HarmonicRatios:
    """Defines the required Fibonacci ratios for one harmonic pattern type."""
    name: str
    symbol: str
    ab_xa: Optional[Tuple[float, float]]   # AB/XA retracement
    bc_ab: Optional[Tuple[float, float]]   # BC/AB retracement
    cd_bc: Optional[Tuple[float, float]]   # CD/BC extension
    ad_xa: Optional[Tuple[float, float]]   # AD/XA retracement (or CD/XC for Cypher)
    use_cd_xc: bool = False                # True for Cypher


GARTLEY = HarmonicRatios(
    name="Gartley", symbol="G",
    ab_xa=(0.618, 0.618),
    bc_ab=(0.382, 0.886),
    cd_bc=(1.272, 1.618),
    ad_xa=(0.786, 0.786),
)

BAT = HarmonicRatios(
    name="Bat", symbol="B",
    ab_xa=(0.382, 0.500),
    bc_ab=(0.382, 0.886),
    cd_bc=(1.618, 2.618),
    ad_xa=(0.886, 0.886),
)

BUTTERFLY = HarmonicRatios(
    name="Butterfly", symbol="BF",
    ab_xa=(0.786, 0.786),
    bc_ab=(0.382, 0.886),
    cd_bc=(1.618, 2.618),
    ad_xa=(1.272, 1.618),
)

CRAB = HarmonicRatios(
    name="Crab", symbol="CR",
    ab_xa=(0.382, 0.618),
    bc_ab=(0.382, 0.886),
    cd_bc=(2.240, 3.618),
    ad_xa=(1.618, 1.618),
)

SHARK = HarmonicRatios(
    name="Shark", symbol="SH",
    ab_xa=None,
    bc_ab=(1.130, 1.618),
    cd_bc=(1.618, 2.236),
    ad_xa=(0.886, 1.130),
)

CYPHER = HarmonicRatios(
    name="Cypher", symbol="CY",
    ab_xa=(0.382, 0.618),
    bc_ab=(1.130, 1.414),
    cd_bc=None,
    ad_xa=(0.786, 0.786),
    use_cd_xc=True,
)

ALL_PATTERNS = [GARTLEY, BAT, BUTTERFLY, CRAB, SHARK, CYPHER]
PATTERN_MAP = {p.name: p for p in ALL_PATTERNS}

PATTERN_TARGETS = {
    "Gartley":   (".618 AD", "1.272 AD"),
    "Bat":       (".618 AD", "1.272 AD"),
    "Butterfly": (".618 AD", "1.272 AD"),
    "Crab":      (".618 AD", "1.618 AD"),
    "Shark":     (".382 AD", "C"),
    "Cypher":    (".618 CD", "1.618 XA"),
}


def compute_target_price(target_type: str, xY: float, aY: float, bY: float, cY: float, dY: float, bull: bool) -> float:
    """Compute target price from target type string."""
    ad = abs(aY - dY)
    cd = abs(cY - dY)
    xa = abs(xY - aY)
    sign = 1.0 if bull else -1.0

    if target_type == ".382 AD":
        return dY + sign * 0.382 * ad
    elif target_type == ".5 AD":
        return dY + sign * 0.500 * ad
    elif target_type == ".618 AD":
        return dY + sign * 0.618 * ad
    elif target_type == "1.272 AD":
        return dY + sign * 1.272 * ad
    elif target_type == "1.618 AD":
        return dY + sign * 1.618 * ad
    elif target_type == ".382 CD":
        return dY + sign * 0.382 * cd
    elif target_type == ".5 CD":
        return dY + sign * 0.500 * cd
    elif target_type == ".618 CD":
        return dY + sign * 0.618 * cd
    elif target_type == "1.272 CD":
        return dY + sign * 1.272 * cd
    elif target_type == "1.618 CD":
        return dY + sign * 1.618 * cd
    elif target_type == "1.618 XA":
        return dY + sign * 1.618 * xa
    elif target_type == "C":
        return cY
    elif target_type == "B":
        return bY
    elif target_type == "A":
        return aY
    else:
        return dY + sign * 0.618 * ad


@dataclass
class HarmonicConfig:
    """General configuration dataclass."""
    min_score: float = 0.85
    risk_per_trade_pct: float = 0.02
    fib_error_pct: float = 15.0
    leg_asymmetry_pct: float = 250.0
    pivot_lengths: List[int] = field(default_factory=lambda: [3, 5, 8])
    trailing_bars: int = 2
    pattern_timeout_mult: float = 3.0
    stop_pct: float = 75.0
    stop_mode: str = "pct_of_t1"
    max_concurrent: int = 2
    initial_equity: float = 10_000.0
    w_ratio_accuracy: float = 4.0
    w_prz_confluence: float = 2.0
    w_d_confluence: float = 3.0
    entry_limit_pct: float = 1.0
    session_start_hour: Optional[int] = None
    session_end_hour: Optional[int] = None
    allowed_days: Optional[List[int]] = None
    enabled_patterns: List[str] = field(default_factory=lambda: ["Cypher", "Gartley", "Crab", "Shark"])
