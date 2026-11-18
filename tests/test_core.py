from reportlab.pdfgen import canvas

from slide_anki_mcp import core


def make_pdf(path, pages):
    c = canvas.Canvas(str(path))
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()


def test_read_and_overview(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Cardiac cycle", "Systole is ventricular contraction"], ["Valves", "Mitral valve has two cusps"]])
    slides = core.read_slides(str(pdf))
    assert len(slides) == 2
    assert core.slide_overview(slides)[0]["title"] == "Cardiac cycle"


def test_overview_warns_on_empty_slide(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps and a long enough line"], []])
    ov = core.slide_overview(core.read_slides(str(pdf)))
    assert ov[0]["warning"] is None and ov[1]["warning"]


def test_check_card_supported_and_unsupported(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps"]])
    slides = core.read_slides(str(pdf))
    ok = core.check_card({"front": "q", "back": "Mitral valve has two cusps", "slide": 1}, slides)
    bad = core.check_card({"front": "q", "back": "Mitral valve has three large cusps", "slide": 1}, slides)
    out = core.check_card({"front": "q", "back": "x y z w", "slide": 9}, slides)
    assert ok["ok"] and not bad["ok"] and not out["ok"]


def test_write_tsv_tags_slide(tmp_path):
    out = core.write_anki_tsv([{"front": "Q", "back": "A", "slide": 4}], str(tmp_path / "o.tsv"))
    assert open(out, encoding="utf-8").read() == "Q\tA\tslides Slide_4\n"


def test_short_wrong_answer_is_rejected(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["ADH is produced in Hypothalamus", "Daily intake is 100 meq"]])
    slides = core.read_slides(str(pdf))
    card = lambda back: core.check_card({"front": "q", "back": back, "slide": 1}, slides)
    assert card("Hypothalamus")["ok"] and card("100 meq")["ok"]
    assert not card("Anterior pituitary")["ok"] and not card("200 meq")["ok"]


def test_match_needs_whole_words(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps", "Give 0.9% saline e.g. in shock"]])
    slides = core.read_slides(str(pdf))
    card = lambda back: core.check_card({"front": "q", "back": back, "slide": 1}, slides)
    assert not card("Mitral valve has tw")["ok"] and not card("itral valve")["ok"]
    assert card("Give 0.9% saline e.g. in shock")["ok"]


def test_bad_card_fields_are_rejected_not_crashing():
    slides = ["Mitral valve has two cusps"]
    good = {"front": "q", "back": "two cusps", "slide": 1}
    for bad in ({"front": "q", "slide": 1}, {**good, "back": ""}, {**good, "back": None},
                {**good, "back": 5}, {"back": "two cusps", "slide": 1}, {**good, "slide": True}):
        assert not core.check_card(bad, slides)["ok"]


def test_export_skips_exact_duplicates(tmp_path):
    from slide_anki_mcp import server
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps"]])
    card = {"front": "Cusps?", "back": "two cusps", "slide": 1}
    other = {**card, "front": "Mitral cusps?"}
    res = server.export_anki(str(pdf), [card, other, dict(card)], str(tmp_path / "o.tsv"))
    assert res["count"] == 2 and res["duplicates_skipped"] == [2]
    assert len(open(res["written"], encoding="utf-8").read().splitlines()) == 2


def test_pdf_with_no_pages_raises(tmp_path):
    from pypdf import PdfWriter
    import pytest
    pdf = tmp_path / "zero.pdf"
    PdfWriter().write(str(pdf))
    with pytest.raises(ValueError):
        core.read_slides(str(pdf))
