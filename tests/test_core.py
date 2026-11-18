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
