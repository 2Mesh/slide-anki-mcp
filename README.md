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
- The check is a whole-word text match after removing case and punctuation. Every part of the answer is checked, short ones too, so a one-word answer must also be on the slide. It catches invented wording, not wrong reasoning, and it rejects correct paraphrases: copy the slide's wording.
- A card with an empty front or back, or a slide number that is not a whole number in range, is rejected.
- Arabic works on a generated test PDF (Arial font, letters shaped and stored right-to-left the way PDF writers do): exact Arabic answers pass, wrong ones fail, and short vowel marks (تشكيل) are ignored. It is not tested on a real Arabic lecture yet. If a PDF stores Arabic in another order, the extracted text comes out reversed and Arabic cards will not match.
- Text extraction quality depends on the PDF.

## Develop

```bash
pip install -e ".[test]"
pytest
```

MIT licensed.
