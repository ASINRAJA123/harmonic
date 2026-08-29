"""
XABCD Harmonic Pattern Scanner.
Assembles 5-point XABCD structures, validates Fibonacci ratios, computes PRZ zones, and scores patterns.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import (
    HarmonicRatios, HarmonicConfig, ALL_PATTERNS, PATTERN_MAP,
    PATTERN_TARGETS, compute_target_price
)


@dataclass
class HarmonicPattern:
    """A detected XABCD harmonic pattern."""
    pattern_type: str
    bull: bool

    x_idx: int
    x_price: float
    a_idx: int
    a_price: float
    b_idx: int
    b_price: float
    c_idx: int
    c_price: float
    d_idx: int
    d_price: float

    r_ab_xa: float = 0.0
    r_bc_ab: float = 0.0
    r_cd_bc: float = 0.0
    r_ad_xa: float = 0.0

    err_ab_xa: float = 0.0
    err_bc_ab: float = 0.0
    err_cd_bc: float = 0.0
    err_ad_xa: float = 0.0

    prz_near: float = 0.0
    prz_far: float = 0.0
    score: float = 0.0

    t1_price: float = 0.0
    t2_price: float = 0.0
    stop_price: float = 0.0
    entry_price: float = 0.0

    entry_bar: Optional[int] = None
    entry_filled: bool = False
    t1_hit: bool = False
    t2_hit: bool = False
    stop_hit: bool = False
    exit_bar: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    realized_pnl: float = 0.0
    lot_size: float = 0.0


def _ratio_error(actual: float, target_min: float, target_max: float) -> float:
    mid = (target_min + target_max) / 2.0
    if target_min <= actual <= target_max:
        return abs(actual - mid) / mid if mid != 0 else 0.0
    elif actual < target_min:
        return abs(actual - target_min) / target_min if target_min != 0 else 1.0
    else:
        return abs(actual - target_max) / target_max if target_max != 0 else 1.0


def _ratio_valid(actual: float, target_range: Optional[Tuple[float, float]], err_pct: float) -> Tuple[bool, float]:
    if target_range is None:
        return True, 0.0

    t_min, t_max = target_range
    tolerance = err_pct / 100.0
    expanded_min = t_min * (1.0 - tolerance)
    expanded_max = t_max * (1.0 + tolerance)

    if expanded_min <= actual <= expanded_max:
        err = _ratio_error(actual, t_min, t_max)
        return True, err
    return False, 1.0


def validate_pattern(
    xP: float, aP: float, bP: float, cP: float, dP: float,
    xI: int, aI: int, bI: int, cI: int, dI: int,
    ratios: HarmonicRatios, cfg, bull: bool
) -> Optional[HarmonicPattern]:
    xa = abs(aP - xP)
    ab = abs(bP - aP)
    bc = abs(cP - bP)
    cd = abs(dP - cP)
    ad = abs(dP - aP)
    xc = abs(cP - xP)

    if xa == 0 or ab == 0 or bc == 0 or cd == 0 or (ratios.use_cd_xc and xc == 0):
        return None

    r_ab_xa = ab / xa
    r_bc_ab = bc / ab
    r_cd_bc = cd / bc
    r_ad_xa = (cd / xc) if ratios.use_cd_xc else (ad / xa)

    v1, e1 = _ratio_valid(r_ab_xa, ratios.ab_xa, cfg.fib_error_pct)
    v2, e2 = _ratio_valid(r_bc_ab, ratios.bc_ab, cfg.fib_error_pct)
    v3, e3 = _ratio_valid(r_cd_bc, ratios.cd_bc, cfg.fib_error_pct)
    v4, e4 = _ratio_valid(r_ad_xa, ratios.ad_xa, cfg.fib_error_pct)

    if not (v1 and v2 and v3 and v4):
        return None

    errors = [e for e, valid in [(e1, ratios.ab_xa), (e2, ratios.bc_ab), (e3, ratios.cd_bc), (e4, ratios.ad_xa)] if valid is not None]
    avg_err = np.mean(errors) if errors else 0.0
    score = max(0.0, 1.0 - (avg_err / getattr(cfg, "fib_error_pct", 15.0)))

    # Exact Institutional Harmonic Invalidation & Take-Profit Targets
    if ratios.name == "Cypher":
        tp1_price = (dP + 0.382 * cd) if bull else (dP - 0.382 * cd)
        tp2_price = (dP + 0.618 * xc) if bull else (dP - 0.618 * xc)
        stop_price = (xP - 0.10 * xa) if bull else (xP + 0.10 * xa)
    elif ratios.name == "Shark":
        tp1_price = (dP + 0.382 * cd) if bull else (dP - 0.382 * cd)
        tp2_price = (dP + 0.500 * cd) if bull else (dP - 0.500 * cd)
        stop_price = (dP - 0.15 * cd) if bull else (dP + 0.15 * cd)
    elif ratios.name == "Gartley":
        tp1_price = (dP + 0.382 * ad) if bull else (dP - 0.382 * ad)
        tp2_price = (dP + 0.618 * ad) if bull else (dP - 0.618 * ad)
        stop_price = (xP - 0.05 * xa) if bull else (xP + 0.05 * xa)
    else:
        tp1_price = (dP + 0.382 * ad) if bull else (dP - 0.382 * ad)
        tp2_price = (dP + 0.618 * ad) if bull else (dP - 0.618 * ad)
        stop_price = (xP - 0.10 * xa) if bull else (xP + 0.10 * xa)

    entry_price = dP

    return HarmonicPattern(
        pattern_type=ratios.name, bull=bull,
        x_idx=xI, x_price=xP, a_idx=aI, a_price=aP,
        b_idx=bI, b_price=bP, c_idx=cI, c_price=cP,
        d_idx=dI, d_price=dP,
        r_ab_xa=r_ab_xa, r_bc_ab=r_bc_ab, r_cd_bc=r_cd_bc, r_ad_xa=r_ad_xa,
        err_ab_xa=e1, err_bc_ab=e2, err_cd_bc=e3, err_ad_xa=e4,
        prz_near=dP, prz_far=dP, score=score,
        t1_price=tp1_price, t2_price=tp2_price,
        stop_price=stop_price, entry_price=entry_price,
    )


def _prz_from_bc(bP: float, cP: float, ratios: HarmonicRatios, bull: bool) -> Optional[float]:
    if ratios.cd_bc is None: return None
    bc = abs(cP - bP)
    mid = (ratios.cd_bc[0] + ratios.cd_bc[1]) / 2.0
    return (cP - bc * mid) if bull else (cP + bc * mid)


def _prz_from_xa(xP: float, aP: float, ratios: HarmonicRatios, bull: bool) -> Optional[float]:
    if ratios.ad_xa is None or ratios.use_cd_xc: return None
    xa = abs(aP - xP)
    mid = (ratios.ad_xa[0] + ratios.ad_xa[1]) / 2.0
    return (aP - xa * mid) if bull else (aP + xa * mid)


def scan_patterns_at_bar(bars, bar_idx, pivot_highs, pivot_lows, cfg, highs, lows):
    return []
