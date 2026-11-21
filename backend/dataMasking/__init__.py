"""Maskowanie danych osobowych w tekście wejściowym, bez LLM.

Zostają imiona i nazwiska; PESEL, NIP, REGON, numery kont i kart, dowody,
paszporty, telefony, e-maile, adresy, kody pocztowe, adresy IP, daty urodzenia
i numery rejestracyjne są zastępowane znacznikami ``[TYP_N]``.

>>> mask_personal_data("Jan Kowalski, tel. 600 100 200").text
'Jan Kowalski, tel. [TELEFON_1]'
"""

from .masker import Entity, MaskingResult, mask_personal_data

__all__ = ["Entity", "MaskingResult", "mask_personal_data"]
