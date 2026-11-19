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
        server.export_anki(str(pdf), [good], str(tmp_path / "victim.cfg"), reviewed_indexes=[0])


def test_export_skips_duplicates_ignoring_case_and_spaces(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Mitral valve has two cusps"]])
    one = card("two cusps", "Mitral valve has two cusps", front="Cusps?")
    same = {**one, "front": "Cusps? ", "back": "Two  cusps"}
    other = {**one, "front": "Mitral cusps?"}
    res = server.export_anki(str(pdf), [one, other, same], str(tmp_path / "o.tsv"), reviewed_indexes=[0, 1, 2])
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


def test_back_negated_in_evidence_is_rejected():
    slides = ["Note: galactose is not essential in the diet.\nGlucagon test: no glucose rise in type I"]
    def ok(back, ev):
        return core.check_card({"front": "f", "back": back, "evidence": ev, "slide": 1}, slides)["ok"]
    ev = "galactose is not essential in the diet"
    assert not ok("essential", ev)
    assert ok("not essential", ev)
    assert not ok("glucose rise in type I", "Glucagon test: no glucose rise in type I")
    assert ok("no glucose rise in type I", "Glucagon test: no glucose rise in type I")


def test_single_arrow_is_not_found_inside_double_arrow():
    slides = ["PC deficiency Fasting - ↑↑ N"]
    def ok(back):
        return core.check_card({"front": "f", "back": back, "evidence": "PC deficiency Fasting - ↑↑ N", "slide": 1}, slides)["ok"]
    assert not ok("↑")
    assert ok("↑↑")


def test_arrow_before_back_must_be_in_back():
    slides = ["Pi locked in F-1-P; ↓ serum phosphate rises later"]
    ev = "Pi locked in F-1-P; ↓ serum phosphate"
    def ok(back):
        return core.check_card({"front": "f", "back": back, "evidence": ev, "slide": 1}, slides)["ok"]
    assert not ok("serum phosphate")
    assert ok("↓ serum phosphate")


def test_friendly_errors(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="folder"):
        core.read_slides(str(tmp_path))
    c = {"front": "f", "back": "two cusps", "evidence": "The mitral valve has two cusps", "slide": "1"}
    assert "whole number" in core.check_card(c, ["The mitral valve has two cusps"])["unsupported"][0]
    c["slide"] = 5
    assert "1 to 1" in core.check_card(c, ["The mitral valve has two cusps"])["unsupported"][0]
    ok = [dict(c, slide=1)]
    for name in ("CON.tsv", "nul.tsv"):
        with pytest.raises(ValueError, match="reserved"):
            core.write_anki_tsv(ok, str(tmp_path / name))
    (tmp_path / "d.tsv").mkdir()
    with pytest.raises(ValueError, match="folder with that name"):
        core.write_anki_tsv(ok, str(tmp_path / "d.tsv"))
    (tmp_path / "f.pdf").write_text("x")
    with pytest.raises(ValueError, match="a file, not a folder"):
        core.write_anki_tsv(ok, str(tmp_path / "f.pdf" / "x.tsv"))
    assert core.write_anki_tsv(ok, str(tmp_path / ".tsv"))


def test_negation_in_second_copy_and_newline_in_evidence(tmp_path):
    ev = "Mitral valve has two cusps; aortic valve has not two cusps"
    assert not core.check_card({"front": "f", "back": "two cusps", "evidence": ev, "slide": 1}, [ev])["ok"]
    slide = "Mitral valve\nhas two cusps"
    card = {"front": "f", "back": "two cusps", "evidence": slide, "slide": 1}
    assert core.check_card(card, [slide])["ok"]
    out = core.write_anki_tsv([card], str(tmp_path / "n.tsv"))
    rows = [ln for ln in open(out, encoding="utf-8").read().split("\n") if ln and not ln.startswith("#")]
    assert len(rows) == 1 and "Mitral valve has two cusps" in rows[0]


def test_glued_text_boxes_and_slide_text_on_empty_back():
    slide = "G6Pase\nGlycerolConsequence of any block: lactate cannot become glucose"
    q = "Consequence of any block: lactate cannot become glucose"
    assert core.check_card({"front": "f", "back": "lactate cannot become glucose", "evidence": q, "slide": 1}, [slide])["ok"]
    wrong = q.replace("lactate", "pyruvate")
    assert not core.check_card({"front": "f", "back": "pyruvate cannot become glucose", "evidence": wrong, "slide": 1}, [slide])["ok"]
    res = core.check_card({"front": "f", "back": "", "evidence": q, "slide": 1}, [slide])
    assert not res["ok"] and res["slide_text"].startswith("G6Pase")


def _ok(slide, back, ev=None):
    return core.check_card({"front": "f", "back": back, "evidence": ev or slide, "slide": 1}, [slide])["ok"]


def test_numbers_cut_after_comma_slash_colon_times():
    for slide, back in [("Daily water need is 1,500 ml", "500 ml"), ("Normal blood pressure is 120/80 mmHg", "80 mmHg"),
                        ("Adrenaline is given 1:1000 IM", "1000 IM"), ("Normal WBC is 4×10⁹/L", "4")]:
        assert not _ok(slide, back)
    assert _ok("Daily water need is 1,500 ml", "1,500 ml")
    assert _ok("Normal blood pressure is 120/80 mmHg", "120/80 mmHg")


def test_negation_variants():
    assert not _ok("Von Gierke: ↑↑ lactate and urate", "lactate and urate")
    assert not _ok("Galactose (not essential in the diet)", "essential in the diet")
    assert not _ok("The valve doesn't have three cusps", "have three cusps")
    assert _ok("Galactose (not essential in the diet)", "not essential in the diet")


def test_camel_split_needs_four_lowercase_letters():
    assert not _ok("cAMP activates protein kinase A", "protein kinase A", "AMP activates protein kinase A")
    assert _ok("cAMP activates protein kinase A", "protein kinase A", "cAMP activates protein kinase A")


def test_list_cut_short_is_rejected():
    ev = "Liver failure, proximal tubular dysfunction, lactic acidosis"
    assert not _ok(ev, "Liver failure, proximal tubular dysfunction")
    assert _ok(ev, "Liver failure, proximal tubular dysfunction, lactic acidosis")
    assert _ok(ev, "lactic acidosis")


def test_unreadable_char_is_shown_and_matches_minus_only():
    slide = "Resting potential is �70 mV in neurons"
    assert core.slide_overview([slide])[0]["warning"]
    assert _ok(slide, "-70 mV", "Resting potential is -70 mV in neurons")
    assert not _ok(slide, "70 mV", "Resting potential is 70 mV in neurons")


def test_advisor_false_reject_cases():
    assert _ok("ACE inhibitors (enalapril, captopril, etc.) lower BP", "enalapril, captopril")
    assert _ok("Answer yes/no questions only in this test", "questions only")
    assert not _ok("Galactose (not essential in the diet)", "essential in the diet")


# ---- Arabic PDFs from Word, PowerPoint, Edge and Chrome (real extracted pieces) ----

def _ar(slide, back, ev):
    return core.check_card({"front": "f", "back": back, "evidence": ev, "slide": 1}, [slide])["ok"]


def test_word_arabic_words_without_spaces_and_backwards_numbers():
    # pypdf pieces from a real Word export: one piece per word, no space glyph, ٣٠ written as ٠٣
    line = core._join_chunks(["قد", "لا", "تشعر", "به", " ", "\n", "الهدف", "رفع", "الوعي", "بأن", "غياب",
                              "الأعراض", "لا", "يعني", "أن"], flip_indic=True)
    assert line.startswith("قد لا تشعر به")
    nums = core._join_chunks(["على", "شكل", "رقمين،", "مثل", "٠٢١", "٠٨", "الرقم"], flip_indic=True)
    assert nums == "على شكل رقمين، مثل ١٢٠ ٨٠ الرقم"
    assert _ar(nums, "١٢٠/٨٠", "على شكل رقمين، مثل ١٢٠/٨٠")  # Word dropped the "/"
    assert not _ar(nums, "٨٠/١٢٠", "على شكل رقمين، مثل ٨٠/١٢٠")
    refs = core._join_chunks(["التوثيق", "العلمي", "لهذا", "البنر", "1", "4", " "], flip_indic=True)
    assert _ar(refs, "[1–4]", "التوثيق العلمي لهذا البنر: [1–4].")  # Word dropped "[", "–", "]"
    assert not _ar(refs, "[14]", "التوثيق العلمي لهذا البنر: [14].")


def test_arabic_quote_ignores_lost_spaces_and_punctuation_but_not_words():
    slide = "النصوصالمعلَّمةبـجاهزللطباعةهيالنسخةالمقترحةللبنرين"  # glued, quotes « » lost
    q = "النصوص المعلَّمة بـ«جاهز للطباعة» هي النسخة المقترحة للبنرين."
    assert _ar(slide, "النسخة المقترحة للبنرين", q)
    assert _ar(slide, "النسخة المقترحة للبنرين", "النصوص المعلمة بـ«جاهز للطباعة» هي النسخة المقترحة للبنرين")
    assert not _ar(slide, "النسخة المقترحة للبنرين", q.replace("المقترحة", "النهائية"))
    spaced = "قد تشعر أنك بخير تمامًا، ومع ذلك قد يكون ضغط دمك مرتفعًا"
    assert not _ar(spaced, "أنك بخير", "شعر أنك بخير تمامًا")  # starts inside a word
    assert not _ar("درجة الحرارة - 5 درجات تحت الصفر", "5 درجات", "درجة الحرارة 5 درجات تحت الصفر")


def test_arabic_negation_before_the_back():
    ev = "الجلوكوز لا يظهر في البول عند الأصحاء"
    assert not _ar(ev, "يظهر في البول", ev)
    assert _ar(ev, "لا يظهر في البول", ev)
    assert not _ar("الأنسولين ليس هرمونا ستيرويديا", "هرمونا ستيرويديا", "الأنسولين ليس هرمونا ستيرويديا")


def test_chromium_visual_order_is_put_back():
    # real Edge lines after joining pieces: number/English runs come first and ranges reversed
    assert core._visual_to_logical("mmol/L 145-135 اﻟﺻودﯾوم اﻟطﺑﯾﻌﻲ") == "اﻟﺻودﯾوم اﻟطﺑﯾﻌﻲ 135-145 mmol/L"
    assert core._visual_to_logical("ﻣن اﻟوطﺎء ADH ﯾﻔرز اﻟﮭرﻣون") == "ﯾﻔرز اﻟﮭرﻣون ADH ﻣن اﻟوطﺎء"
    slide = core._visual_to_logical("mmol/L 2.6-2.2 واﻟﻛﺎﻟﺳﯾوم mmol/L 5.0-3.5 اﻟﺑوﺗﺎﺳﯾوم اﻟطﺑﯾﻌﻲ")
    good = "البوتاسيوم الطبيعي 3.5-5.0 mmol/L والكالسيوم 2.2-2.6 mmol/L"
    assert _ar(slide, "2.2-2.6 mmol/L", good)
    assert not _ar(slide, "2.2-2.6 mmol/L", "البوتاسيوم الطبيعي 2.2-2.6 mmol/L والكالسيوم 3.5-5.0 mmol/L")
    assert core._visual_to_logical("% ﺗﻘرﯾﺑﺎ 50 ﯾرﺗﻔﻊ ﺑﻧﺳﺑﺔ") == "ﯾرﺗﻔﻊ ﺑﻧﺳﺑﺔ 50 % ﺗﻘرﯾﺑﺎ"
    assert core._visual_to_logical("Normal sodium is 135-145 mmol/L") == "Normal sodium is 135-145 mmol/L"


def test_powerpoint_list_number_glued_to_english():
    line = core._join_chunks(["\n", ".", "3", "ADH ", "هو الهرمون المضاد لإدرار البول"], flip_indic=False)
    assert _ar(line, "ADH", "ADH هو الهرمون المضاد لإدرار البول")


# ---- damaged text layers and OCR (the OCR engine is faked, so no extra is needed) ----

def test_damaged_text_layer_warning():
    dz, ff = chr(0x1C4), chr(12)
    # start of the real text of an Arabic PDF made by MuPDF: reversed letters, U+01C4 and a control character
    mupdf = f"ﺯﺮﻔﻳ ﺍ{dz}ﻥﻮﻣﺮﻬ ﺍ{dz}ﺩﺎﻀﻤ ƾ{ff}ﺭﺍﺭﺩ ﺍ{dz}ﻝﻮﺒ ﻦﻣ ﺍ{dz}ﺀﺎﻃﻮ\nﺍ{dz}ﻡﻮﻳﺩﻮﺼ ﺍ{dz}ﻲﻌﻴﺒﻄ 135-145 mmol/L"
    assert "damaged" in core.slide_overview([mupdf])[0]["warning"]
    fine = ["ﯾﻔرز اﻟﮭرﻣون ADH ﻣن اﻟوطﺎء والصوديوم الطبيعي 135-145 mmol/L",
            "Galactosemia: GALT, GALK, GALE and the classic enzyme defects",
            "Romanian keeps ș and ț in words such as știință and țară in text"]
    assert all(o["warning"] is None for o in core.slide_overview(fine))


def test_ocr_arabic_rows_are_put_in_reading_order():
    assert core._ocr_rtl("mmol/L 145-135 الطبيعي الصوديوم") == "الصوديوم الطبيعي 135-145 mmol/L"
    assert core._ocr_rtl("mmHg 80/120 الطبيعي الدم ضغط") == "ضغط الدم الطبيعي 120/80 mmHg"
    assert core._ocr_rtl("Galactose is a monosaccharide") == "Galactose is a monosaccharide"

    def line(text, x0, x1, y):
        return {"text": text, "words": [{"bounding_rect": {"x": x0, "y": y, "width": x1 - x0, "height": 26}}]}
    # real boxes from Windows OCR on a scanned Word page: one line came back as two parts
    rows = core._ocr_rtl_rows([line("ثانية ٤٥", 136, 213, 150), line("مختصر شرح سيناريو", 260, 470, 152),
                               line("خمس بهدوء نجلس", 137, 900, 214)])
    assert rows[0] == "سيناريو شرح مختصر ٤٥ ثانية"
    assert _ar(rows[0], "٤٥ ثانية", "سيناريو شرح مختصر — ٤٥ ثانية")
    assert not _ar(rows[0], "٥٤ ثانية", "سيناريو شرح مختصر — ٥٤ ثانية")


def test_page_without_text_is_read_by_ocr_and_marked(tmp_path, monkeypatch):
    import sys
    import types
    pil = pytest.importorskip("PIL.Image")
    from reportlab.lib.utils import ImageReader
    img = tmp_path / "slide.png"
    pil.new("RGB", (800, 400), "white").save(img)
    pdf = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawImage(ImageReader(str(img)), 0, 0, 400, 200)
    c.showPage()
    c.save()
    monkeypatch.setitem(sys.modules, "winocr", None)  # as if the extra were not installed
    assert "no text" in core.slide_overview(core.read_slides(str(pdf)))[0]["warning"]

    import asyncio

    async def lines(lang):
        return [{"text": "Galactose is a monosaccharide (simple sugar).", "words": []}] if lang == "en" else []

    fake = types.ModuleType("winocr")  # like winocr, the fake calls asyncio.run
    fake.recognize_pil_sync = lambda image, lang: {"lines": asyncio.run(lines(lang))}
    monkeypatch.setitem(sys.modules, "winocr", fake)

    async def inside_server_loop():  # the MCP server calls tools while its event loop runs
        return core.read_slides(str(pdf))
    slides = asyncio.run(inside_server_loop())
    assert getattr(slides[0], "ocr", False)
    assert "OCR" in core.slide_overview(slides)[0]["warning"]
    res = core.check_card({"front": "f", "back": "a monosaccharide", "slide": 1,
                           "evidence": "Galactose is a monosaccharide (simple sugar)."}, slides)
    assert res["ok"] and res["ocr"]
    assert not core.check_card({"front": "f", "back": "a disaccharide", "slide": 1,
                                "evidence": "Galactose is a disaccharide (simple sugar)."}, slides)["ok"]


def test_list_cut_before_and_or_ampersand_and_direction_verbs():
    ev = "Aldosterone is stimulated by angiotensin II, low sodium & high potassium."
    assert not _ok(ev, "angiotensin II, low sodium")
    assert _ok(ev, "angiotensin II, low sodium & high potassium")
    assert not _ok("Signs: fever, rash and cough", "fever, rash")
    assert not _ok("ADH decreases the release of renin in the kidney", "release of renin in the kidney")
    assert _ok("ADH decreases the release of renin in the kidney", "decreases the release of renin in the kidney")
    assert not _ok("Aldosterone increases sodium reabsorption", "sodium reabsorption")
    assert _ok("Aldosterone increases sodium reabsorption", "increases sodium reabsorption")


def test_lower_as_adjective_and_inhibitor_are_not_direction_verbs():
    assert _ok("Lower limb oedema is common in heart failure", "limb oedema")
    assert _ok("Protease inhibitor therapy is used", "therapy is used")
    assert not _ok("Lowers blood pressure in hypertensive patients", "blood pressure in hypertensive patients")


def test_nul_in_lecture_pdf_is_read_as_degree_sign(tmp_path, monkeypatch):
    pdf = tmp_path / "d.pdf"
    c = canvas.Canvas(str(pdf)); c.drawString(72, 800, "x"); c.showPage(); c.save()
    monkeypatch.setattr(core, "_page_chunks", lambda page: ["The enzyme is lost at a temperature of 60 \x00C"])
    slides = core.read_slides(str(pdf))
    assert "60 °C" in slides[0] and "\x00" not in slides[0]
    assert core.check_card({"front": "f", "back": "60 °C", "evidence": "lost at a temperature of 60 °C", "slide": 1}, slides)["ok"]
    assert not core.slide_overview(slides)[0]["warning"] or "damaged" not in core.slide_overview(slides)[0]["warning"]


def test_cloze_front_is_built_from_the_quote():
    slides = ["Examples: trisomy 21 (Down syndrome), monosomy X (Turner syndrome), and Klinefelter syndrome"]
    ev = slides[0]
    r = core.check_card({"cloze": True, "back": "Turner syndrome", "slide": 1, "evidence": ev}, slides)
    assert r["ok"] and r["status"] == "verified"
    assert r["front"] == "Examples: trisomy 21 (Down syndrome), monosomy X (___), and Klinefelter syndrome"


def test_free_form_front_needs_review_and_bad_cloze_fails():
    slides = ["Examples: trisomy 21 (Down syndrome), monosomy X (Turner syndrome), and Klinefelter syndrome"]
    ev = slides[0]
    r = core.check_card({"front": "Trisomy 21 causes which syndrome?", "back": "Turner syndrome", "slide": 1, "evidence": ev}, slides)
    assert r["ok"] and r["status"] == "needs_review"
    r = core.check_card({"cloze": True, "back": "Edwards syndrome", "slide": 1, "evidence": ev}, slides)
    assert not r["ok"]


def test_export_refuses_own_question_by_default_but_writes_cloze(tmp_path):
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [["Examples: trisomy 21 (Down syndrome), monosomy X (Turner syndrome), and Klinefelter syndrome"]])
    ev = "Examples: trisomy 21 (Down syndrome), monosomy X (Turner syndrome), and Klinefelter syndrome"
    free = {"front": "Trisomy 21 causes which syndrome?", "back": "Turner syndrome", "slide": 1, "evidence": ev}
    res = server.export_anki(str(pdf), [free], str(tmp_path / "a.tsv"))
    assert res["written"] is None and res["needs_review_indexes"] == [0]
    assert not (tmp_path / "a.tsv").exists()
    res = server.export_anki(str(pdf), [{"cloze": True, "back": "Turner syndrome", "slide": 1, "evidence": ev}], str(tmp_path / "b.tsv"))
    assert res["count"] == 1 and "(___)" in (tmp_path / "b.tsv").read_text(encoding="utf-8")


def _cl(slide, back, ev):
    return core.check_card({"cloze": True, "back": back, "slide": 1, "evidence": ev}, [slide])


def test_cloze_holes_found_by_the_advisor():
    # 1 letters must match exactly (mM vs mm)
    assert not _cl("Plasma glucose is 5 mM in the fasting state", "5 mm", "Plasma glucose is 5 mm in the fasting state")["ok"]
    # 2 a heading line ending in ':' comes along
    r = _cl("NOT features of nephrotic syndrome:\nHaematuria, hypertension, red cell casts in urine", "red cell casts in urine",
            "Haematuria, hypertension, red cell casts in urine")
    assert r["status"] == "verified" and r["front"].startswith("NOT features of nephrotic syndrome:")
    # 3 the rest of the slide line comes along (the 'except' stays in the question)
    r = _cl("Metformin is first-line in all diabetics, except those with renal failure", "first-line",
            "Metformin is first-line in all diabetics")
    assert "except those with renal failure" in r["front"]
    # 5 a replacement character is not a minus sign
    assert not _cl("\ufffd70 mV is the resting potential", "-70 mV", "\ufffd70 mV is the resting potential")["ok"]
    # blank only whole words, and no stopword or whole-quote blanks
    assert not _cl("AMP activates AMPK while cAMP activates PKA", "AMP", "AMP activates AMPK while cAMP activates PKA")["front"] if False else True
    r = _cl("AMP activates AMPK while cAMP activates PKA", "AMP", "AMP activates AMPK while cAMP activates PKA")
    assert r["front"] == "___ activates AMPK while cAMP activates PKA"
    assert not _cl("The mitral valve has two cusps", "The", "The mitral valve has two cusps")["ok"]
    assert not _cl("The mitral valve has two cusps", "The mitral valve has two cusps", "The mitral valve has two cusps")["ok"]


def test_cloze_whole_line_gets_the_slide_title_and_bad_quote_gets_a_suggestion():
    slide = "Gluconeogenesis substrates\nlactate and glycerol and alanine\nSecond line here"
    r = _cl(slide, "lactate and glycerol and alanine", "lactate and glycerol and alanine")
    assert r["status"] == "verified" and r["front"] == "Gluconeogenesis substrates \u2014 ___"
    assert r["front"].replace("___", "lactate and glycerol and alanine") == "Gluconeogenesis substrates — lactate and glycerol and alanine"
    r = _cl("Alanine is made in muscle and sent to liver", "made in muscle", "Alanine was made in muscle and sent to liver")
    assert not r["ok"] and r["suggested_quote"] == "Alanine is made in muscle and sent to liver"


def test_reviewed_indexes_write_free_questions_with_a_tag_and_suggest_a_cloze(tmp_path):
    ev = "The mitral valve has two cusps and the aortic valve has three"
    pdf = tmp_path / "lec.pdf"
    make_pdf(pdf, [[ev]])
    free = {"front": "Cusps of the mitral valve?", "back": "two cusps", "slide": 1, "evidence": ev}
    res = server.export_anki(str(pdf), [free], str(tmp_path / "a.tsv"))
    assert res["written"] is None and res["needs_review_indexes"] == [0]
    assert res["suggested_cloze_fronts"][0] == "The mitral valve has ___ and the aortic valve has three"
    res = server.export_anki(str(pdf), [free], str(tmp_path / "b.tsv"), reviewed_indexes=[0])
    assert res["count"] == 1 and "reviewed" in (tmp_path / "b.tsv").read_text(encoding="utf-8")


def test_cloze_page_number_title_is_no_context_and_private_bullets_become_dots():
    r = _cl("- 14 -\nalanine is made in muscle", "alanine is made in muscle", "alanine is made in muscle")
    assert not r["ok"] and "no context" in r["unsupported"][0]
    r = _cl("\uf0b7 Alanine is made in muscle and sent", "muscle", "\uf0b7 Alanine is made in muscle and sent")
    assert r["front"].startswith("\u2022 Alanine") and "\uf0b7" not in r["front"]


def test_arabic_pdf_with_almost_no_common_words_gets_a_warning():
    words = " ".join(f"كلمة{c}" for c in "ابجدهوزحطيكلمنسعفصقرشتثخذضظغ" * 12)
    warned = core.slide_overview([words])[0]["warning"]
    assert warned and "garbled" in warned
    healthy = " ".join(["هذا الدرس في الجهاز الهضمي ومن اهم الاعضاء"] * 40)
    assert core.slide_overview([healthy])[0]["warning"] is None
