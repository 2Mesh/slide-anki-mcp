"""Pure logic: read slides from a PDF, check cards against them, write Anki TSV."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pypdf import PdfReader


def _norm(text: str) -> str:
    """Lowercase and collapse whitespace/punctuation so matching ignores layout."""
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def read_slides(pdf_path: str) -> list[str]:
    """Return the text of each page (slide), index 0 = slide 1."""
    reader = PdfReader(pdf_path)
    return [(page.extract_text() or "").replace("�", "-").strip() for page in reader.pages]


MIN_TEXT_CHARS = 40


def slide_overview(slides: list[str]) -> list[dict]:
    out = []
    for i, text in enumerate(slides, start=1):
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        out.append({
            "slide": i,
            "title": first[:80],
            "chars": len(text),
            "warning": "little or no text (image slide?): cannot make cards from it"
            if len(text) < MIN_TEXT_CHARS else None,
        })
    return out


def check_card(card: dict, slides: list[str]) -> dict:
    """Flag a card whose answer is not supported by the slide it cites.

    The answer is split into fragments (by newline or ';' or '.'); every
    fragment longer than 3 words must appear in the slide text after
    normalisation. Short fragments are ignored to avoid false alarms.
    """
    page = card.get("slide")
    result = {"slide": page, "ok": True, "unsupported": []}
    if not isinstance(page, int) or not 1 <= page <= len(slides):
        result.update(ok=False, unsupported=["slide number missing or out of range"])
        return result
    slide_norm = _norm(slides[page - 1])
    for frag in re.split(r"[\n;.]+", card.get("back", "")):
        words = _norm(frag)
        if len(words.split()) > 3 and words not in slide_norm:
            result["unsupported"].append(frag.strip())
    result["ok"] = not result["unsupported"]
    return result


def write_anki_tsv(cards: list[dict], out_path: str, deck_tag: str = "slides") -> str:
    """Write an Anki-importable tab-separated file: Front, Back, Tags.

    Each card gets a tag like ``Slide_12`` so the source stays visible in Anki.
    """
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        for card in cards:
            tag = f"{deck_tag} Slide_{card['slide']}"
            writer.writerow([card["front"], card["back"], tag])
    return str(path.resolve())
