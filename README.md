# slide-anki-mcp

An MCP server that turns lecture PDFs into Anki cards without letting the model invent anything.

Study tools often write cards from the model's own knowledge. If your exam is graded against your lecturer's slides, that is a risk. This server makes the model cite a slide for every card, then **rejects any card whose answer is not found in that slide's text**.

## Tools

| Tool | What it does |
|---|---|
| `list_slides(pdf_path)` | Slide numbers with first line and length |
| `get_slide(pdf_path, slide)` | Exact text of one slide |
| `check_cards(pdf_path, cards)` | Flags answer fragments not present in the cited slide |
| `export_anki(pdf_path, cards, out_path)` | Writes an Anki-importable `.tsv` (Front, Back, Tags), only if every card passes; each card is tagged `Slide_N` |

A card is `{"front": "...", "back": "...", "slide": 12}`.

## Install

```bash
pip install slide-anki-mcp   # after it is published; until then: pip install .
```

Add to Claude Code:

```bash
claude mcp add slide-anki -- slide-anki-mcp
```

## Use

Ask Claude: "Read lecture.pdf with slide-anki and make cards from slides 3 to 10, then export to cards.tsv." In Anki: File → Import, choose the `.tsv`, set field separator to Tab.

## Limits

- Works on PDFs with real text. Image-only slides have no text, so `list_slides` warns and no cards can be checked against them. Scanned decks need OCR first. (Tried on a real 40-slide lecture: 4 slides had no text at all and 7 more had under 40 characters, mostly section titles.)
- The check is a text match after removing case and punctuation. It catches invented wording, not wrong reasoning, and short fragments (3 words or fewer) are ignored.
- Text extraction quality depends on the PDF.

## Develop

```bash
pip install -e ".[test]"
pytest
```

MIT licensed.
