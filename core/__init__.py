"""
Harmonic Pattern Quantitative Trading System — Core Package.
"""

from .config import HarmonicRatios, HarmonicConfig, ALL_PATTERNS, PATTERN_MAP
from .swing_detector import detect_pivots, collect_swings
from .pattern_scanner import HarmonicPattern, validate_pattern, scan_patterns_at_bar
from .engine import HarmonicV3Config, run_harmonic_v3_backtest, HarmonicV3Trade, resample_bars

__version__ = "3.0.0"
