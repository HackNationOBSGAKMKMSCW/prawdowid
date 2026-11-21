"""Uruchamia cały katalog przypadków (patrz OCZEKIWANE_WYNIKI.md)."""

import os

import pytest

from .katalog import ALL_CASES


def _param(c):
    marks = []
    if c.known_bug:
        marks.append(pytest.mark.xfail(strict=True, reason=c.known_bug))
    if c.group == "LV":
        marks.append(
            pytest.mark.skipif(os.getenv("RUN_LLM_TESTS") != "1", reason="ustaw RUN_LLM_TESTS=1")
        )
    return pytest.param(c, id=c.id, marks=marks)


@pytest.mark.parametrize("case", [_param(c) for c in ALL_CASES])
def test_przypadek(case):
    case.check()
