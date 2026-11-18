"""MCP server exposing slide reading, card checking and Anki export."""

from mcp.server.fastmcp import FastMCP

from . import core

mcp = FastMCP("slide-anki")


@mcp.tool()
def list_slides(pdf_path: str) -> list[dict]:
    """List every slide in a lecture PDF with its first line and text length."""
    return core.slide_overview(core.read_slides(pdf_path))


@mcp.tool()
def get_slide(pdf_path: str, slide: int) -> str:
    """Return the exact text of one slide (1-based)."""
    slides = core.read_slides(pdf_path)
    if not 1 <= slide <= len(slides):
        raise ValueError(f"slide must be between 1 and {len(slides)}")
    return slides[slide - 1]


@mcp.tool()
def check_cards(pdf_path: str, cards: list[dict]) -> list[dict]:
    """Check each card {front, back, slide} against the text of its slide.

    Returns one result per card. 'unsupported' lists answer fragments that do
    not appear in the cited slide, so wording the doctor never used is caught.
    """
    slides = core.read_slides(pdf_path)
    return [core.check_card(c, slides) for c in cards]


@mcp.tool()
def export_anki(pdf_path: str, cards: list[dict], out_path: str) -> dict:
    """Write cards to an Anki-importable .tsv, refusing cards not supported by their slide."""
    slides = core.read_slides(pdf_path)
    checks = [core.check_card(c, slides) for c in cards]
    bad = [i for i, c in enumerate(checks) if not c["ok"]]
    if bad:
        return {"written": None, "rejected_card_indexes": bad, "details": [checks[i] for i in bad]}
    return {"written": core.write_anki_tsv(cards, out_path), "count": len(cards)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
