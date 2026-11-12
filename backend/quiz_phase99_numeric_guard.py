"""Phase99: conservative, model-independent numerical translation integrity check.

Scope intentionally excludes multi-value mappings, bare numbers and quantities whose
units cannot be compared safely. This module never modifies a learner answer or a PDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import unicodedata


@dataclass(frozen=True)
class Quantity:
    text: str
    value: Decimal
    family: str
    base_value: Decimal


@dataclass(frozen=True)
class QuantityConflict:
    source: Quantity
    learner: Quantity


# ASCII spellings and common Japanese forms. The third member is the factor
# converting a value into a canonical unit within the same physical dimension.
_UNIT_ROWS = (
    ("hours", "time", "3600"), ("hour", "time", "3600"),
    ("hrs", "time", "3600"), ("hr", "time", "3600"),
    ("h", "time", "3600"), ("時間", "time", "3600"),
    ("minutes", "time", "60"), ("minute", "time", "60"),
    ("mins", "time", "60"), ("min", "time", "60"),
    ("分", "time", "60"),
    ("seconds", "time", "1"), ("second", "time", "1"),
    ("secs", "time", "1"), ("sec", "time", "1"),
    ("s", "time", "1"), ("秒", "time", "1"),
    ("％", "percent", "1"), ("%", "percent", "1"),
    ("°c", "celsius", "1"), ("℃", "celsius", "1"),
    ("degrees", "angle", "1"), ("degree", "angle", "1"),
    ("deg", "angle", "1"), ("°", "angle", "1"), ("度", "angle", "1"),
    ("GPa", "pressure", "1e9"), ("MPa", "pressure", "1e6"),
    ("kPa", "pressure", "1e3"), ("Pa", "pressure", "1"),
    ("GeV", "energy", "1e9"), ("MeV", "energy", "1e6"),
    ("keV", "energy", "1e3"), ("eV", "energy", "1"),
    ("GHz", "frequency", "1e9"), ("MHz", "frequency", "1e6"),
    ("kHz", "frequency", "1e3"), ("Hz", "frequency", "1"),
    ("km", "length", "1000"), ("cm", "length", "0.01"),
    ("mm", "length", "0.001"), ("um", "length", "0.000001"),
    ("μm", "length", "0.000001"), ("µm", "length", "0.000001"),
    ("nm", "length", "0.000000001"), ("m", "length", "1"),
    ("mT", "magnetic_field", "0.001"), ("T", "magnetic_field", "1"),
    ("kA", "current", "1000"), ("mA", "current", "0.001"),
    ("A", "current", "1"), ("mV", "voltage", "0.001"),
    ("V", "voltage", "1"), ("kW", "power", "1000"),
    ("W", "power", "1"), ("mK", "kelvin", "0.001"),
    ("K", "kelvin", "1"),
    ("Ω·m", "resistivity", "1"), ("Ωm", "resistivity", "1"),
    ("ohm·m", "resistivity", "1"), ("ohm m", "resistivity", "1"),
)

# Prefer longer spellings (e.g. mm over m).  Order only affects scanning, not value.
_UNITS = sorted(_UNIT_ROWS, key=lambda item: len(item[0]), reverse=True)
_UNIT_PART = "|".join(re.escape(unit) for unit, _, _ in _UNITS)
_QUANTITY_RE = re.compile(
    r"(?<![A-Za-z0-9_.])"
    r"(?P<number>[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s*(?P<unit>" + _UNIT_PART + r")"
    r"(?![A-Za-z])", re.IGNORECASE,
)
_FACTORS = {label.lower(): (family, Decimal(factor)) for label, family, factor in _UNIT_ROWS}

# In mathematical markup 1.4 x 10^n is not a plain 1.4 of anything.
# Treat these as ambiguous, not as guaranteed equal or wrong.
_POWER_TOKEN = re.compile(r"(?:\d+\s*[×x]\s*10\s*(?:\^|[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]))|(?:10\s*\^)")


def extract_quantities(text: str) -> tuple[Quantity, ...]:
    normalized = unicodedata.normalize("NFKC", text or "")
    if _POWER_TOKEN.search(normalized):
        return ()
    rows: list[Quantity] = []
    for m in _QUANTITY_RE.finditer(normalized):
        unit_text = m.group("unit")
        unit_spec = _FACTORS.get(unit_text.lower())
        if unit_spec is None:
            continue
        try:
            value = Decimal(m.group("number"))
        except InvalidOperation:
            continue
        family, factor = unit_spec
        rows.append(Quantity(m.group(0).strip(), value, family, value * factor))
    return tuple(rows)


def find_unambiguous_conflicts(source_text: str, learner_answer: str) -> tuple[QuantityConflict, ...]:
    """Only flag single-vs-single physical dimensions with confidently different values.

    Two values of the same dimension may express a range, a pairing, an explicit
    correction, or alternative units; those cases require a semantic judge and
    are deliberately excluded here. Missing values are handled by existing audits.
    """
    sources = extract_quantities(source_text)
    learners = extract_quantities(learner_answer)
    source_families: dict[str, list[Quantity]] = {}
    learner_families: dict[str, list[Quantity]] = {}
    for q in sources:
        source_families.setdefault(q.family, []).append(q)
    for q in learners:
        learner_families.setdefault(q.family, []).append(q)
    conflicts = []
    for family, src in source_families.items():
        dest = learner_families.get(family, [])
        if len(src) != 1 or len(dest) != 1:
            continue
        original, observed = src[0], dest[0]
        # Decimal gives exact SI-unit conversion. Small rounding discrepancies
        # are not automatically promoted to a critical mistranslation.
        tolerance = max(abs(original.base_value) * Decimal("0.005"), Decimal("1e-18"))
        if abs(original.base_value - observed.base_value) > tolerance:
            conflicts.append(QuantityConflict(source=original, learner=observed))
    return tuple(conflicts)
