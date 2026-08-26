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

    # Leg symmetry
    leg_bars = [aI - xI, bI - aI, cI - bI, dI - cI]
    avg_bars = np.mean(leg_bars)
    if avg_bars > 0:
        for lb in leg_bars:
            asym = abs(lb - avg_bars) / avg_bars * 100
            if asym > getattr(cfg, "leg_asymmetry_pct", 250.0):
                return None

    # PRZ calculation
    prz_bc_ext = _prz_from_bc(bP, cP, ratios, bull)
    prz_xa_ext = _prz_from_xa(xP, aP, ratios, bull)
    prz_levels = [l for l in [prz_bc_ext, prz_xa_ext] if l is not None]

    if len(prz_levels) >= 2:
        prz_near = min(prz_levels, key=lambda x: abs(x - dP))
        prz_far = max(prz_levels, key=lambda x: abs(x - dP))
    elif len(prz_levels) == 1:
        prz_near = prz_far = prz_levels[0]
    else:
        prz_near = prz_far = dP

    errors = [e for e, valid in [(e1, ratios.ab_xa), (e2, ratios.bc_ab), (e3, ratios.cd_bc), (e4, ratios.ad_xa)] if valid is not None]
    avg_err = np.mean(errors) if errors else 0.0
    ratio_score = 1.0 - avg_err

    prz_range = abs(prz_near - prz_far) if prz_near != prz_far else 0.001
    prz_confluence_score = max(0, 1.0 - (prz_range / (xa * 0.1)))
    d_to_prz = min(abs(dP - prz_near), abs(dP - prz_far))
    d_confluence_score = max(0, 1.0 - (d_to_prz / (xa * 0.05)))

    w_ratio = getattr(cfg, "w_ratio_accuracy", 4.0)
    w_prz = getattr(cfg, "w_prz_confluence", 2.0)
    w_d = getattr(cfg, "w_d_confluence", 3.0)
    total_w = w_ratio + w_prz + w_d

    score = (w_ratio * ratio_score + w_prz * prz_confluence_score + w_d * d_confluence_score) / total_w
    score = max(0.0, min(1.0, score))

    t1_type, t2_type = PATTERN_TARGETS.get(ratios.name, (".618 AD", "1.272 AD"))
    t1_price = compute_target_price(t1_type, xP, aP, bP, cP, dP, bull)
    t2_price = compute_target_price(t2_type, xP, aP, bP, cP, dP, bull)

    entry_price = dP
    dist_to_t1 = abs(t1_price - entry_price)
    pct = getattr(cfg, "stop_pct", 75.0) / 100.0
    stop_price = (entry_price - dist_to_t1 * pct) if bull else (entry_price + dist_to_t1 * pct)

    return HarmonicPattern(
        pattern_type=ratios.name, bull=bull,
        x_idx=xI, x_price=xP, a_idx=aI, a_price=aP,
        b_idx=bI, b_price=bP, c_idx=cI, c_price=cP,
        d_idx=dI, d_price=dP,
        r_ab_xa=r_ab_xa, r_bc_ab=r_bc_ab, r_cd_bc=r_cd_bc, r_ad_xa=r_ad_xa,
        err_ab_xa=e1, err_bc_ab=e2, err_cd_bc=e3, err_ad_xa=e4,
        prz_near=prz_near, prz_far=prz_far, score=score,
        t1_price=t1_price, t2_price=t2_price,
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
