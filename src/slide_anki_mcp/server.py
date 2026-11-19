"""MCP server exposing slide reading, card checking and Anki export."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import core

mcp = FastMCP("slide-anki")


@mcp.tool()
def list_slides(pdf_path: str) -> list[dict]:
    """List every slide in a lecture PDF (full path) with its first line and text length.

    A slide with a 'warning' has little or no text. Cards cannot be checked against it.
    """
    return core.slide_overview(core.read_slides(pdf_path))


@mcp.tool()
def get_slide(pdf_path: str, slide: int) -> str:
    """Return the exact text of one slide (1-based). Copy evidence quotes from this text."""
    slides = core.read_slides(pdf_path)
    if not 1 <= slide <= len(slides):
        raise ValueError(f"slide must be between 1 and {len(slides)}")
    return slides[slide - 1]


@mcp.tool()
def check_cards(pdf_path: str, cards: list[dict]) -> list[dict]:
    """Check each card {front, back, slide, evidence} against the text of its slide.

    'evidence' must be a quote of at least 4 words copied exactly from the cited
    slide, and 'back' must be inside that quote. Symbols, signs and numbers must
    match exactly. A passing card means the quote is on the slide. It does not
    mean the card is correct: read the evidence next to the answer. A failing
    card comes back with the slide text so the quote can be fixed.
    """
    slides = core.read_slides(pdf_path)
    return [core.check_card(c, slides) for c in cards]


@mcp.tool()
def export_anki(pdf_path: str, cards: list[dict], out_path: str) -> dict:
    """Write cards to a new Anki-importable .tsv, only if every card passes check_cards.

    out_path must end with .tsv, be in an existing folder, and must not exist yet.
    The evidence quote and slide number are written at the end of each answer.
    Exact duplicates (same front and back) are written once; the indexes of the
    skipped copies are listed in 'duplicates_skipped'.
    """
    path = Path(out_path)
    if path.suffix.lower() != ".tsv":
        raise ValueError("out_path must end with .tsv")
    slides = core.read_slides(pdf_path)
    checks = [core.check_card(c, slides) for c in cards]
    bad = [i for i, c in enumerate(checks) if not c["ok"]]
    if bad:
        return {"written": None, "rejected_card_indexes": bad, "details": [checks[i] for i in bad]}
    seen, unique, dupes = set(), [], []
    for i, c in enumerate(cards):
        key = core.card_key(c)
        if key in seen:
            dupes.append(i)
        else:
            seen.add(key)
            unique.append(c)
    return {"written": core.write_anki_tsv(unique, out_path), "count": len(unique),
            "duplicates_skipped": dupes}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
