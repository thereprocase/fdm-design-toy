"""Check results and verdicts shared by every rule checker (PLAN D13, D16).

A result never says a bare PASS: it carries the check level reached, whether the binding value is
provisional, and what the check does and does not establish. NOT_CHECKED is used whenever a check
could not actually run as specified; it is never folded into PASS.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

LEVELS = ("V", "M", "T", "P")          # density field, mesh, toolpath, physical coupon
AUTHORITY = {"P": 3, "T": 2, "M": 1, "V": 0}   # a higher level overrides a lower one


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_CHECKED = "NOT_CHECKED"          # the check could not run as specified
    NOT_CALIBRATED = "NOT_CALIBRATED"    # no calibrated value exists for this combination


@dataclass
class CheckResult:
    rule: str
    level: str
    verdict: Verdict
    message: str
    provisional: bool = True             # binding value is a heuristic / T0 / uncalibrated
    metrics: dict = field(default_factory=dict)
    fixes: list[str] = field(default_factory=list)
    establishes: str = ""
    does_not_establish: str = ""

    def __post_init__(self):
        if self.level not in LEVELS:
            raise ValueError(f"unknown check level {self.level!r}; expected one of {LEVELS}")
        self.verdict = Verdict(self.verdict)

    @property
    def label(self) -> str:
        """Verdict as shown to people: PROVISIONAL is never dropped."""
        tag = " (PROVISIONAL)" if self.provisional and self.verdict in (Verdict.PASS, Verdict.FAIL) else ""
        return f"{self.rule} {self.level} {self.verdict.value}{tag}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


def governing(results: list[CheckResult]) -> dict[str, CheckResult]:
    """Per rule, the result from the highest level that actually ran (T overrides M overrides V).

    Results that did not run (NOT_CHECKED) never govern while a run result exists at any level.
    """
    best: dict[str, CheckResult] = {}
    for r in results:
        ran = r.verdict is not Verdict.NOT_CHECKED
        cur = best.get(r.rule)
        if cur is None:
            best[r.rule] = r
            continue
        cur_ran = cur.verdict is not Verdict.NOT_CHECKED
        if (ran, AUTHORITY[r.level]) > (cur_ran, AUTHORITY[cur.level]):
            best[r.rule] = r
    return best
