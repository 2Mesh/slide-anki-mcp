import csv
import os

import pytest
from reportlab.pdfgen import canvas

from slide_anki_mcp import core, server


def make_pdf(path, pages):
    c = canvas.Canvas(str(path))
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()


def card(back, evidence, slide=1, front="q"):
    return {"front": front, "back": back, "evidence": evidence, "slide": slide}


def check(slide_text, *args, **kw):
    return core.check_card(card(*args, **kw), [slide_text])


def reasons(res):
    return " ".join(res["unsupported"])


# ---- reading and overview -------------------------------------------------

def test_read_and_overview(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Cardiac cycle", "Systole is ventricular contraction"], ["Valves", "Mitral valve has two cusps"]])
    slides = core.read_slides(str(pdf))
    assert len(slides) == 2
    assert core.slide_overview(slides)[0]["title"] == "Cardiac cycle"


def test_overview_warns_on_empty_and_short_slides(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps and a long enough line"], ["Valves"], []])
    ov = core.slide_overview(core.read_slides(str(pdf)))
    assert ov[0]["warning"] is None
    assert "under 40" in ov[1]["warning"]
    assert "no text" in ov[2]["warning"]


def test_pdf_with_no_pages_raises(tmp_path):
    from pypdf import PdfWriter
    pdf = tmp_path / "zero.pdf"
    PdfWriter().write(str(pdf))
    with pytest.raises(ValueError):
        core.read_slides(str(pdf))


def test_missing_and_non_pdf_files_give_clear_errors(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        core.read_slides(str(tmp_path / "nope.pdf"))
    junk = tmp_path / "junk.pdf"
    junk.write_text("this is not a pdf")
    with pytest.raises(ValueError, match="cannot read"):
        core.read_slides(str(junk))


# ---- the evidence check ---------------------------------------------------

SLIDE = "Mitral valve\nThe mitral valve has two cusps"


def test_supported_card_passes_and_wrong_answer_fails():
    ok = check(SLIDE, "two cusps", "The mitral valve has two cusps")
    bad = check(SLIDE, "three large cusps", "The mitral valve has three large cusps")
    assert ok["ok"] and not bad["ok"]
    assert "not on this slide" in reasons(bad)
    assert "The mitral valve has two cusps" in bad["slide_text"]


def test_short_wrong_answer_is_rejected():
    slide = "ADH is produced in Hypothalamus\nDaily intake is 100 meq"
    assert check(slide, "Hypothalamus", "ADH is produced in Hypothalamus")["ok"]
    assert not check(slide, "Anterior pituitary", "ADH is produced in Anterior pituitary")["ok"]
    assert not check(slide, "200 meq", "Daily intake is 200 meq")["ok"]


def test_comparison_and_sign_symbols_are_kept():
    slide = "Normal K is > 3.5 mmol/L. Resting potential is -70 mV"
    assert check(slide, "> 3.5 mmol/L", "Normal K is > 3.5 mmol/L")["ok"]
    assert not check(slide, "< 3.5 mmol/L", "Normal K is < 3.5 mmol/L")["ok"]
    assert check(slide, "-70 mV", "Resting potential is -70 mV")["ok"]
    assert not check(slide, "+70 mV", "Resting potential is +70 mV")["ok"]
    # the back cannot drop the sign that the evidence keeps
    assert not check(slide, "70 mV", "Resting potential is -70 mV")["ok"]


def test_superscripts_do_not_become_plain_digits():
    slide = "Count is 10\u2075 cells per mL in blood"
    assert check(slide, "10\u2075 cells", "Count is 10\u2075 cells per mL")["ok"]
    assert not check(slide, "105 cells", "Count is 105 cells per mL")["ok"]
    assert core._text("10\u2075") != core._text("105")


def test_a_cut_range_is_rejected():
    slide = "Daily intake is 1000-1500 ml of water"
    assert check(slide, "1000-1500 ml", "Daily intake is 1000-1500 ml")["ok"]
    assert not check(slide, "1500 ml", "Daily intake is 1000-1500 ml")["ok"]


def test_negation_is_visible_in_the_evidence_not_detected():
    """Known limit: the check cannot judge meaning. The quote is exported so a
    human can see 'does not have' next to the answer."""
    slide = "Mitral valve does not have three cusps"
    res = check(slide, "three cusps", "Mitral valve does not have three cusps")
    assert res["ok"]


def test_evidence_must_be_long_enough_and_exactly_on_the_slide():
    assert "too short" in reasons(check(SLIDE, "two cusps", "two cusps"))
    assert "not on this slide" in reasons(check(SLIDE, "two cusps", "The itral valve has two cusps"))
    assert "not on this slide" in reasons(check(SLIDE, "two cusps", "The mitral valve has tw"))
    assert "not on this slide" in reasons(check(SLIDE, "two cusps", "The mitral valve has two large cusps"))


def test_back_must_be_inside_the_evidence():
    res = check(SLIDE, "two cusps and a flap", "The mitral valve has two cusps")
    assert "back is not inside" in reasons(res)


def test_word_hyphenated_at_a_line_break_still_matches():
    slide = "Muscle contrac-\ntion needs calcium ions"
    assert check(slide, "Muscle contraction", "Muscle contraction needs calcium ions")["ok"]


def test_slide_without_text_is_rejected_loudly():
    for empty in ("", "  ", "\u25cf"):
        res = check(empty, "two cusps", "The mitral valve has two cusps")
        assert not res["ok"] and "cannot verify" in reasons(res)


def test_bad_card_fields_are_rejected_not_crashing():
    slides = [SLIDE]
    good = card("two cusps", "The mitral valve has two cusps")
    bads = [{k: v for k, v in good.items() if k != "evidence"}, {k: v for k, v in good.items() if k != "front"},
            {**good, "back": ""}, {**good, "back": None}, {**good, "back": 5}, {**good, "evidence": 7},
            {**good, "slide": True}, {**good, "slide": 0}, {**good, "slide": 9}, "a string", None, 5]
    for bad in bads:
        assert not core.check_card(bad, slides)["ok"], bad


# ---- exporting ------------------------------------------------------------

def rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        text = [ln for ln in fh.read().splitlines(keepends=True)]
    header = [ln.rstrip("\n") for ln in text if ln.startswith("#") and not ln.startswith('"#')]
    body = [ln for ln in text if ln not in [h + "\n" for h in header]]
    return header, list(csv.reader(body, delimiter="\t"))


def test_tsv_has_header_quotes_everything_and_shows_the_evidence(tmp_path):
    cards = [{"front": "#1 valve?", "back": "two cusps", "slide": 4,
              "evidence": "The mitral valve has two cusps"}]
    out = core.write_anki_tsv(cards, str(tmp_path / "o.tsv"))
    header, body = rows(out)
    assert header == ["#separator:tab", "#html:false", "#tags column:3"]
    assert body == [["#1 valve?", "two cusps  |  Source (slide 4): The mitral valve has two cusps",
                     "slides Slide_4"]]
    assert open(out, encoding="utf-8").read().splitlines()[3].startswith('"#1 valve?"')


def test_export_refuses_wrong_extension_existing_file_and_missing_folder(tmp_path):
    cards = [{"front": "q", "back": "A", "slide": 1, "evidence": "The mitral valve has two cusps"}]
    victim = tmp_path / "victim.cfg"
    victim.write_text("keep me")
    with pytest.raises(ValueError, match=".tsv"):
        core.write_anki_tsv(cards, str(victim))
    assert victim.read_text() == "keep me"
    existing = tmp_path / "taken.tsv"
    existing.write_text("keep me too")
    with pytest.raises(ValueError, match="already exists"):
        core.write_anki_tsv(cards, str(existing))
    assert existing.read_text() == "keep me too"
    with pytest.raises(ValueError, match="folder"):
        core.write_anki_tsv(cards, str(tmp_path / "no_such" / "x.tsv"))
    assert not (tmp_path / "no_such").exists()


def test_server_export_checks_before_writing(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps"]])
    good = card("two cusps", "Mitral valve has two cusps", front="Cusps?")
    bad = card("three cusps", "Mitral valve has three cusps", front="Cusps?")
    res = server.export_anki(str(pdf), [good, bad], str(tmp_path / "o.tsv"))
    assert res["written"] is None and res["rejected_card_indexes"] == [1]
    assert not (tmp_path / "o.tsv").exists()
    with pytest.raises(ValueError, match=".tsv"):
        server.export_anki(str(pdf), [good], str(tmp_path / "victim.cfg"))


def test_export_skips_duplicates_ignoring_case_and_spaces(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps"]])
    one = card("two cusps", "Mitral valve has two cusps", front="Cusps?")
    same = {**one, "front": "Cusps? ", "back": "Two  cusps"}
    other = {**one, "front": "Mitral cusps?"}
    res = server.export_anki(str(pdf), [one, other, same], str(tmp_path / "o.tsv"))
    assert res["count"] == 2 and res["duplicates_skipped"] == [2]
    assert len(rows(res["written"])[1]) == 2


# ---- Arabic ---------------------------------------------------------------

ARABIC_FONTS = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/tahoma.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def test_arabic_slide_matches(tmp_path):
    """Store Arabic as shaped letters in display (right-to-left) order, as a PDF may."""
    arabic_reshaper = pytest.importorskip("arabic_reshaper")
    bidi = pytest.importorskip("bidi.algorithm")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font = next((f for f in ARABIC_FONTS if os.path.exists(f)), None)
    if font is None:
        pytest.skip("no Arabic-capable font found")
    pdfmetrics.registerFont(TTFont("ArabicTest", font))
    pdf = tmp_path / "ar.pdf"
    c = canvas.Canvas(str(pdf))
    c.setFont("ArabicTest", 16)
    c.drawString(72, 800, bidi.get_display(arabic_reshaper.reshape("الكلية تنظم توازن الماء")))
    c.showPage()
    c.save()
    slides = core.read_slides(str(pdf))
    full = "الكلية تنظم توازن الماء"
    assert core.check_card(card(full, full), slides)["ok"]
    assert core.check_card(card("تُنظّم توازن", full), slides)["ok"]
    assert not core.check_card(card("القلب ينظم توازن الماء", "القلب ينظم توازن الماء"), slides)["ok"]


# ---- review round 2: cuts inside a token, invisible characters ------------

def test_quote_or_back_cut_inside_a_number_or_unit_is_rejected():
    slide = "Normal sodium is 135-145 mmol/L\nPump moves Na+ out\nCount is 14.5 per mL"
    assert not check(slide, "135", "Normal sodium is 135")["ok"]
    assert not check("Dose 140 mmol/L daily", "140 mmol", "Dose 140 mmol")["ok"]
    assert not check(slide, "14", "Count is 14")["ok"]
    assert not check(slide, "Na", "Pump moves Na")["ok"]
    assert check(slide, "135-145 mmol/L", "Normal sodium is 135-145 mmol/L")["ok"]
    assert check(slide, "Na+", "Pump moves Na+ out")["ok"]


def test_invisible_characters_and_kept_hyphens_in_pdf_text():
    soft = "con­traction needs calcium ions"
    assert check(soft, "contraction", "contraction needs calcium ions")["ok"]
    wrapped = "Water-\nsoluble vitamins are stored briefly"
    assert check(wrapped, "Water-soluble vitamins", "Water-soluble vitamins are stored briefly")["ok"]
    assert check(wrapped, "Watersoluble vitamins", "Watersoluble vitamins are stored briefly")["ok"]


def test_directory_named_like_the_output_file_is_a_clear_error(tmp_path):
    (tmp_path / "x.tsv").mkdir()
    cards = [{"front": "q", "back": "A", "slide": 1, "evidence": "The mitral valve has two cusps"}]
    with pytest.raises(ValueError):
        core.write_anki_tsv(cards, str(tmp_path / "x.tsv"))


def test_arabic_from_edge_pdf_persian_letter_forms():
    # real text taken from a PDF printed by Microsoft Edge: Persian-style yeh/heh, no space before Latin
    slides = ["ﯾﻔرز اﻟﮭرﻣون اﻟﻣﺿﺎد ﻹدرار اﻟﺑول ﻣن اﻟوطﺎء", "ﯾﻔرز ﻣن اﻟوطﺎء وﯾزﯾد إﻋﺎدة اﻣﺗﺻﺎص اﻟﻣﺎءADH (vasopressin)"]
    q = "يفرز الهرمون المضاد لإدرار البول من الوطاء"
    assert core.check_card({"front": "f", "back": q, "evidence": q, "slide": 1}, slides)["ok"]
    bad = q.replace("الوطاء", "الدماغ")
    assert not core.check_card({"front": "f", "back": bad, "evidence": bad, "slide": 1}, slides)["ok"]
    q2 = "يفرز من الوطاء ويزيد إعادة امتصاص الماء"
    assert core.check_card({"front": "f", "back": q2, "evidence": q2, "slide": 2}, slides)["ok"]
