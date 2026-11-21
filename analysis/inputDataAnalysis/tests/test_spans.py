from inputDataAnalysis.spans import locate_quote

TEXT = "Rząd przyjął ustawę. To skandaliczna zdrada „elit” wobec narodu!"


def test_exact():
    start, end = locate_quote(TEXT, "skandaliczna zdrada")
    assert TEXT[start:end] == "skandaliczna zdrada"


def test_case_and_quote_marks_insensitive():
    start, end = locate_quote(TEXT, 'TO SKANDALICZNA ZDRADA "elit"')
    assert TEXT[start:end] == "To skandaliczna zdrada „elit”"


def test_fuzzy_minor_differences():
    # LLM pominął cudzysłowy wokół „elit”
    span = locate_quote(TEXT, "skandaliczna zdrada elit wobec narodu")
    assert span is not None
    assert "zdrada" in TEXT[span[0] : span[1]]


def test_rejects_hallucinated_quote():
    assert locate_quote(TEXT, "minister ukradł miliardy złotych") is None
    assert locate_quote(TEXT, "xyz") is None
    assert locate_quote(TEXT, "") is None
