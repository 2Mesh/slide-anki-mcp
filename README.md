# slide-anki-mcp

An MCP server that turns lecture PDFs into Anki cards without letting the model invent anything.

Study tools often write cards from the model's own knowledge. If your exam is graded against your lecturer's slides, that is a risk. This server makes the model cite a slide for every card, then **rejects any card whose answer is not found in that slide's text**.

## Tools

| Tool | What it does |
|---|---|
| `list_slides(pdf_path)` | Slide numbers with first line and length |
| `get_slide(pdf_path, slide)` | Exact text of one slide |
| `check_cards(pdf_path, cards)` | Flags answer fragments not present in the cited slide |
| `export_anki(pdf_path, cards, out_path)` | Writes an Anki-importable `.tsv` (Front, Back, Tags), only if every card passes; each card is tagged `Slide_N`, and exact duplicate cards are written once |

A card is `{"front": "...", "back": "...", "slide": 12}`.

## Install

Needs Python 3.10 or newer.

```bash
pip install slide-anki-mcp   # after it is published; until then, from this folder: pip install .
```

### Claude Code

```bash
claude mcp add slide-anki -- slide-anki-mcp
```

### Claude Desktop

Open `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`, macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`), add the server, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "slide-anki": {
      "command": "slide-anki-mcp"
    }
  }
}
```

If Claude cannot find the command, put its full path in `"command"`. You can get the path with `where slide-anki-mcp` on Windows or `which slide-anki-mcp` on macOS and Linux.

## Use

Ask Claude: "Read lecture.pdf with slide-anki and make cards from slides 3 to 10, then export to cards.tsv." Then in Anki: File → Import and choose the `.tsv`. The file starts with header lines (`#separator:tab`, `#html:false`, `#tags column:3`) that Anki 2.1.54 and newer read, so you should not need to change the import settings. Older Anki versions need the field separator set to Tab by hand.

### Example

Made with a small two-slide test PDF. Slide 1 says "ADH is produced in the hypothalamus", slide 2 says "Normal plasma sodium is 135-145 mmol/L".

The model calls `check_cards` with one wrong card and one right card:

```json
{"pdf_path": "lecture.pdf", "cards": [
  {"front": "Where is ADH produced?", "back": "Anterior pituitary", "slide": 1},
  {"front": "Normal plasma sodium?", "back": "135-145 mmol/L", "slide": 2}
]}
```

Result:

```json
[
  {"slide": 1, "ok": false, "unsupported": ["Anterior pituitary"]},
  {"slide": 2, "ok": true, "unsupported": []}
]
```

After fixing the first answer to "The hypothalamus" (and sending the sodium card twice by mistake), `export_anki` returns:

```json
{"written": "/path/to/cards.tsv", "count": 2, "duplicates_skipped": [2]}
```

and the file contains:

```
#separator:tab
#html:false
#tags column:3
Where is ADH produced?	The hypothalamus	slides Slide_1
Normal plasma sodium?	135-145 mmol/L	slides Slide_2
```

If any card fails, `export_anki` writes nothing and returns the failing card indexes and details instead.

## How the check works and what it cannot catch

The server reads the text of each PDF page with `pypdf`. For each card it takes the back and splits it into parts at new lines, `;` and full stops that end a sentence. Each part is lowercased, punctuation is turned into spaces, and it must then appear as whole words, in the same order, in the text of the slide the card cites. If any part is missing, the card fails and that part is listed under `unsupported`.

What this catches:

- Answers in words the slide does not use, including short ones: "Anterior pituitary" fails on a slide that only says "hypothalamus".
- Changed numbers: "200 meq" fails on a slide that says "100 meq".
- A card that cites a slide which does not contain its answer, an empty front or back, or a slide number that is not a whole number in range.

What it cannot catch:

- **Meaning.** It checks words, not sense. If the slide says "Furosemide does not cause hyperkalemia", the card "Does furosemide cause hyperkalemia?" with the back "cause hyperkalemia" passes, because those words are on the slide.
- **The front of the card.** Only the back is checked. A question that asks something the slide does not answer, with a back copied from the slide, still passes.
- **Paraphrases.** A correct answer in other words is rejected. Copy the slide's wording.
- **Images.** Text inside pictures, scanned pages and diagrams is not read. `list_slides` warns when a slide has less than 40 characters of text. On one real 40-slide lecture, 4 slides had no text at all and 7 more had under 40 characters, mostly section titles.
- **Bad text extraction.** If the PDF stores text in an odd way, the extracted words can be split or out of order, and correct cards will fail.

### Arabic

Arabic works on a generated test PDF (Arial or DejaVu font, letters shaped and stored in right-to-left display order with `arabic-reshaper` and `python-bidi`): exact Arabic answers pass, wrong ones fail, and short vowel marks (تشكيل) are ignored. It is not tested on a real Arabic lecture yet. If a PDF stores Arabic in another order, the extracted text comes out reversed and Arabic cards will not match.

## Roadmap

These are real gaps, not promises:

- **OCR for image slides**, so text in pictures and scanned decks can be checked.
- **Meaning-aware checking**, so a correct paraphrase can pass and a phrase taken out of context can be caught.
- **Testing on real Arabic lectures.**

## Develop

```bash
pip install -e ".[test]"
pytest
python tests/e2e_stdio.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed.
