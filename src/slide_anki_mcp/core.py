"""Pure logic: read slides from a PDF, check cards against them, write Anki TSV.

The check is an evidence check. Every card must carry ``evidence``: a quote
copied from the cited slide. The server confirms the quote is really on that
slide (symbols, signs and numbers kept exactly) and that the answer sits inside
the quote. It cannot tell whether the card means what the slide means: the
quote is written into the exported card so the student can read it.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

MIN_TEXT_CHARS = 40  # list_slides warns below this
MIN_WORD_CHARS = 5  # fewer word characters than this = "no text"
MIN_EVIDENCE_WORDS = 4

_SUPER = str.maketrans({
    "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4", "⁵": "^5", "⁶": "^6",
    "⁷": "^7", "⁸": "^8", "⁹": "^9", "⁺": "^+", "⁻": "^-",
    "₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4", "₅": "_5", "₆": "_6",
    "₇": "_7", "₈": "_8", "₉": "_9",
    "–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
})


def _text(s: str, join_hyphen: bool = True) -> str:
    """Make text comparable without losing symbols, signs or digits.

    Only layout is ignored: case, runs of whitespace, a word split by a hyphen
    at a line break, dash and quote styles. Superscripts become ^n so that
    "10⁵" never turns into "105". NFKC turns Arabic presentation forms (which
    PDFs may store) back into normal letters; Arabic short vowels are dropped.
    """
    s = s.translate(_SUPER)
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Mn", "Cf"))
    s = re.sub(r"(?<=[^\W\d_])-[ \t]*\r?\n[ \t]*(?=[^\W\d_])", "" if join_hyphen else "-", s)
    return re.sub(r"\s+", " ", s).strip().casefold().strip(" .;:,")


def _contains(haystack: str, needle: str) -> bool:
    """True if needle is in haystack as whole words, not cut from a longer token.

    "1500 ml" is not found in "1000-1500 ml", and "70 mv" is not found in "-70 mv".
    """
    if not needle:
        return False
    pattern = r"(?<![\w.+\-<>^])" + re.escape(needle) + r"(?![\w^+\-/%]|[.,]\d)"
    return re.search(pattern, haystack) is not None


def read_slides(pdf_path: str) -> list[str]:
    """Return the text of each page (slide), index 0 = slide 1."""
    try:
        reader = PdfReader(pdf_path)
        pages = list(reader.pages)
    except FileNotFoundError:
        raise ValueError(f"file not found: {pdf_path}") from None
    except Exception as exc:  # pypdf raises several error types for bad files
        raise ValueError(f"cannot read {pdf_path} as a PDF: {exc}") from None
    if not pages:
        raise ValueError("PDF has no pages")
    return [(page.extract_text() or "").replace("�", "-").strip() for page in pages]


def _has_text(slide: str) -> bool:
    return len(re.findall(r"\w", slide)) >= MIN_WORD_CHARS


def slide_overview(slides: list[str]) -> list[dict]:
    out = []
    for i, text in enumerate(slides, start=1):
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        warning = None
        if not _has_text(text):
            warning = "slide has no text, cannot verify cards against it"
        elif len(text) < MIN_TEXT_CHARS:
            warning = "under 40 characters of text: may be an image or title slide"
        out.append({"slide": i, "title": first[:80], "chars": len(text), "warning": warning})
    return out


def _fail(result: dict, *problems: str) -> dict:
    result["ok"] = False
    result["unsupported"].extend(problems)
    return result


def check_card(card: dict, slides: list[str]) -> dict:
    """Check one card {front, back, slide, evidence}. Never raises on bad input.

    Passes only if: the slide has text; the evidence is a quote of at least
    4 words that is literally on the cited slide; and the back is inside the
    evidence. Returns ``ok`` and ``unsupported`` (the reasons). When a card
    fails, the slide text is returned too so the model can quote it correctly.
    """
    result = {"slide": None, "ok": True, "unsupported": []}
    if not isinstance(card, dict):
        return _fail(result, "card must be an object with front, back, slide, evidence")
    page = card.get("slide")
    result["slide"] = page
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= len(slides):
        return _fail(result, "slide number missing or out of range")
    slide = slides[page - 1]
    front, back, evidence = card.get("front"), card.get("back"), card.get("evidence")
    for name, value in (("front", front), ("back", back), ("evidence", evidence)):
        if not isinstance(value, str) or not _text(value):
            _fail(result, f"{name} must be non-empty text")
    if result["unsupported"]:
        return result
    if not _has_text(slide):
        return _fail(result, "slide has no text, cannot verify")
    slide_t, ev_t, back_t = _text(slide), _text(evidence), _text(back)
    if len(ev_t.split()) < MIN_EVIDENCE_WORDS:
        _fail(result, f"evidence too short: quote a full sentence or line (at least {MIN_EVIDENCE_WORDS} words)")
    elif not (_contains(slide_t, ev_t) or _contains(_text(slide, join_hyphen=False), ev_t)):
        _fail(result, "evidence is not on this slide exactly as quoted")
    elif not _contains(ev_t, back_t):
        _fail(result, "the back is not inside the evidence quote")
    if not result["ok"]:
        result["slide_text"] = slide[:3000]
    return result


def card_key(card: dict) -> tuple[str, str]:
    return _text(card["front"]), _text(card["back"])


def write_anki_tsv(cards: list[dict], out_path: str, deck_tag: str = "slides") -> str:
    """Write an Anki-importable tab-separated file: Front, Back, Tags.

    The back ends with the slide number and the evidence quote, so the student
    sees the source beside every answer. Every field is quoted, so a front that
    starts with '#' is not read as a header line. The header lines tell Anki
    2.1.54+ the separator, plain text and tags column. Refuses any path that is
    not a new ``.tsv`` file in an existing folder.
    """
    path = Path(out_path)
    if path.suffix.lower() != ".tsv":
        raise ValueError("out_path must end with .tsv")
    if not path.parent.is_dir():
        raise ValueError(f"folder does not exist: {path.parent}")
    try:
        fh = path.open("x", newline="", encoding="utf-8")
    except FileExistsError:
        raise ValueError(f"file already exists, choose a new name: {path}") from None
    except OSError as exc:  # for example a folder with that name, or no permission
        raise ValueError(f"cannot create {path}: {exc.strerror or exc}") from None
    with fh:
        fh.write("#separator:tab\n#html:false\n#tags column:3\n")
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_ALL)
        for card in cards:
            back = f"{card['back']}  |  Source (slide {card['slide']}): {card['evidence']}"
            writer.writerow([card["front"], back, f"{deck_tag} Slide_{card['slide']}"])
    return str(path.resolve())
