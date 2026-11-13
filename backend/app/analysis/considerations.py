"""Considerations: notes on one result, derived from facts about the run by rules in config/considerations.toml.

A rule has a code, a level (info | caution | warning), an origin (where the choice comes from: analyse-together,
this-api or config), a message template and conditions on facts. Wording and thresholds are edited in the TOML file;
Python only supplies the facts (facts.py).
"""
from __future__ import annotations

import operator
import os
import string
from pathlib import Path
from typing import Any

from .facts import FACTS
from .models import Consideration

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "config" / "considerations.toml"
OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq,
       "!=": operator.ne}
LEVELS = ("info", "caution", "warning")
ORIGINS = ("analyse-together", "this-api", "config")
SCOPES = ("run", "level", "place")
PLACE_FACTS = {"place_query", "place_candidates", "place_chosen", "place_alternatives"}
LEVEL_FACTS = {"level_name", "level_type", "level_limit", "level_verified", "period_days", "days_with_data",
               "ambiguous_days", "period_mean", "mean_uncertainty", "level_uncertain"}


def _template_facts(message: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(message) if name}


def load_rules(path: Path | None = None) -> list[dict]:
    path = path or Path(os.environ.get("HL_CONSIDERATIONS_FILE", DEFAULT_FILE))
    with open(path, "rb") as fh:
        rules = tomllib.load(fh).get("rule", [])
    seen = set()
    for r in rules:
        where = f"{path}: rule '{r.get('code')}'"
        if not {"code", "level", "origin", "message"} <= r.keys():
            raise ValueError(f"{where} needs code, level, origin and message")
        if r["code"] in seen:
            raise ValueError(f"{where} is defined twice")
        seen.add(r["code"])
        r.setdefault("scope", "run")
        r.setdefault("when", [])
        if r["level"] not in LEVELS or r["origin"] not in ORIGINS or r["scope"] not in SCOPES:
            raise ValueError(f"{where} has an invalid level, origin or scope")
        used = _template_facts(r["message"]) | {c["fact"] for c in r["when"]}
        unknown = used - FACTS.keys()
        if unknown:
            raise ValueError(f"{where} refers to unknown facts {sorted(unknown)}")
        if r["scope"] == "run" and used & (LEVEL_FACTS | PLACE_FACTS):
            raise ValueError(f"{where} uses per-level or per-place facts but has scope 'run'")
        if any(c["op"] not in OPS for c in r["when"]):
            raise ValueError(f"{where} has an unknown operator")
    return rules


def evaluate(rules: list[dict], facts: dict[str, Any], scope: str = "run") -> list[Consideration]:
    """The rules of `scope` whose conditions hold. A rule whose facts are missing (None) does not apply."""
    out = []
    for r in rules:
        if r["scope"] != scope:
            continue
        conditions = r["when"]
        if any(facts.get(c["fact"]) is None for c in conditions):
            continue
        if not all(OPS[c["op"]](facts[c["fact"]], c["value"]) for c in conditions):
            continue
        names = _template_facts(r["message"])
        if any(facts.get(n) is None for n in names):
            continue
        shown = {n: facts[n] for n in [*dict.fromkeys(c["fact"] for c in conditions), *sorted(names)]}
        out.append(Consideration(code=r["code"], level=r["level"], origin=r["origin"],
                                 message=r["message"].format_map(facts), facts=shown))
    return out
