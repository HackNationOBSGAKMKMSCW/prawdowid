"""Zbiorczy katalog wszystkich przypadków w kolejności grup."""

from .case_base import GROUPS, Case
from .cases_analysis import MA_CASES, PI_CASES, PR_CASES, SC_CASES, SP_CASES, TS_CASES
from .cases_dates import DI_CASES, DT_CASES, DW_CASES, FM_CASES, RE_CASES, WD_CASES
from .cases_live import LV_CASES
from .cases_rules import BD_CASES, RU_CASES, SK_CASES

_ALL = [
    *DT_CASES, *DW_CASES, *DI_CASES, *RE_CASES, *WD_CASES, *FM_CASES, *SP_CASES, *TS_CASES,
    *RU_CASES, *SK_CASES, *BD_CASES, *MA_CASES, *SC_CASES, *PR_CASES, *PI_CASES, *LV_CASES,
]  # fmt: skip
_order = {g: i for i, g in enumerate(GROUPS)}
ALL_CASES: list[Case] = sorted(_ALL, key=lambda c: _order[c.group])  # sort stabilny
assert len({c.id for c in ALL_CASES}) == len(ALL_CASES), "zduplikowane ID przypadków"
