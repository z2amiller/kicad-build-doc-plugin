"""BOM grouping and humanized value sorting for KiCad pedal boards.

Python 3.9 compatible — no match/case, no |union syntax, no tomllib.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Reference designator groups
# ---------------------------------------------------------------------------

RESISTORS = "RESISTORS"
DIODES = "DIODES"
TRANSISTORS = "TRANSISTORS"
CAPACITORS = "CAPACITORS"
OTHER = "OTHER"

BOM_GROUP_ORDER: List[str] = [RESISTORS, DIODES, TRANSISTORS, CAPACITORS, OTHER]

# Regex patterns for each group — order matters: more-specific first.
# CAPACITORS must match C* and CP* (but NOT C alone as a letters-only ref).
# Note: RV*, SW*, LED*, J* all fall through to OTHER.
_GROUP_PATTERNS: List[Tuple[str, re.Pattern]] = [  # type: ignore[type-arg]
    (RESISTORS, re.compile(r"^R\d+$", re.IGNORECASE)),
    (DIODES, re.compile(r"^D\d+$", re.IGNORECASE)),
    (TRANSISTORS, re.compile(r"^Q\d+$", re.IGNORECASE)),
    (CAPACITORS, re.compile(r"^CP?\d+$", re.IGNORECASE)),
]


def bom_group(ref: str) -> str:
    """Return the BOM group name for a reference designator.

    Examples:
        bom_group("R1")   -> "RESISTORS"
        bom_group("RV1")  -> "OTHER"   (potentiometer, not a resistor)
        bom_group("CP1")  -> "CAPACITORS"
        bom_group("D3")   -> "DIODES"
        bom_group("LED1") -> "OTHER"
    """
    for group, pattern in _GROUP_PATTERNS:
        if pattern.match(ref):
            return group
    return OTHER


# ---------------------------------------------------------------------------
# Humanized value sorting
# ---------------------------------------------------------------------------

# SI suffix multipliers.
# Lowercase p/n/u are the canonical forms; uppercase P/N/U are also accepted
# because KiCad sometimes exports values like "100UF" or "10PF".
# IMPORTANT: 'm' (milli, 1e-3) and 'M' (mega, 1e6) are intentionally distinct —
# do NOT fold these together.
_SI_SUFFIXES: Dict[str, float] = {
    "p": 1e-12,
    "P": 1e-12,  # uppercase pico (KiCad variant)
    "n": 1e-9,
    "N": 1e-9,   # uppercase nano (KiCad variant)
    "u": 1e-6,
    "U": 1e-6,   # uppercase micro (KiCad variant)
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# Trailing unit characters to strip before parsing (Ω, R, F, H).
# IMPORTANT: do NOT use re.IGNORECASE here — 'm' is the milli SI suffix and
# must not be stripped.  Only strip unambiguous unit letters: R (ohm shorthand),
# F (farads), H (henries), Ω and variants, and the literal "ohm" suffix.
_UNIT_STRIP_RE = re.compile(r"([RFHΩ]|ohm)$")

# Pattern: optional digits+decimal, optional SI suffix.
# Case-sensitive: 'm' = milli (1e-3), 'M' = mega (1e6), 'K'/'k' = kilo.
# Uppercase P/N/U are accepted as pico/nano/micro variants (see _SI_SUFFIXES).
_VALUE_RE = re.compile(r"^([0-9]*\.?[0-9]+)\s*([pPnNuUmkKMG])?")
# Known limitation: European "letter-as-decimal" notation (e.g. "4R7" = 4.7Ω,
# "0R1" = 100mΩ, "1M0" = 1MΩ) is not parsed — these sort as 4, 0, and 1 resp.
# Uncommon in KiCad BOM exports but could be added if needed.


def humanized_value_key(value: str) -> Tuple[int, float, str]:
    """Return a sort key tuple for a component value string.

    The tuple is (is_numeric, numeric_val, original) where:
    - is_numeric: 0 for numeric values, 1 for non-numeric (so numeric sorts first)
    - numeric_val: the floating-point magnitude
    - original: the raw string (for stable tie-breaking)

    SI suffixes are normalised:
        "100K" -> (0, 100_000.0, "100K")
        "1M"   -> (0, 1_000_000.0, "1M")
        "4.7uF"-> (0, 4.7e-6, "4.7uF")
    """
    stripped = _UNIT_STRIP_RE.sub("", value.strip())
    m = _VALUE_RE.match(stripped)
    if not m:
        return (1, 0.0, value)

    numeric_str = m.group(1)
    suffix = m.group(2) or ""

    try:
        base = float(numeric_str)
    except ValueError:
        return (1, 0.0, value)

    multiplier = _SI_SUFFIXES.get(suffix, 1.0)
    return (0, base * multiplier, value)


# ---------------------------------------------------------------------------
# BOM sorting
# ---------------------------------------------------------------------------

_REF_SORT_RE = re.compile(r"([A-Za-z_]+)(\d*)")


def _ref_sort_key(ref: str) -> Tuple[str, int]:
    """Sort key: alphabetical prefix, then numeric suffix."""
    m = _REF_SORT_RE.match(ref)
    prefix = m.group(1).upper() if m else ref.upper()
    num = int(m.group(2)) if m and m.group(2) else 0
    return (prefix, num)


def sort_bom(entries: List[Dict]) -> List[Dict]:
    """Return a new list of BOM entry dicts sorted by group order then by ref.

    Each entry must have a 'ref' key. Entries are grouped per BOM_GROUP_ORDER
    (RESISTORS, DIODES, TRANSISTORS, CAPACITORS, OTHER).  Within each group,
    entries are sorted by reference designator (alphabetical prefix, then
    numerically by suffix).
    """
    group_buckets: Dict[str, List[Dict]] = {g: [] for g in BOM_GROUP_ORDER}
    for entry in entries:
        ref = entry.get("ref", "")
        group = bom_group(ref)
        group_buckets[group].append(entry)

    result: List[Dict] = []
    for group in BOM_GROUP_ORDER:
        bucket = group_buckets[group]
        bucket.sort(key=lambda e: _ref_sort_key(e.get("ref", "")))
        result.extend(bucket)
    return result
