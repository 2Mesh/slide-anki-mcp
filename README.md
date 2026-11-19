# slide-anki-mcp

[![tests](https://github.com/2Mesh/slide-anki-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/2Mesh/slide-anki-mcp/actions/workflows/test.yml)

An MCP server for students who study from lecture slides. It makes Claude (or any MCP client) quote the slide for every Anki card, and it rejects a card when the quote is not really on that slide.

Study tools often write cards from the model's own knowledge. If your exam is graded against your lecturer's slides, that is a risk. Here every card carries a quote from the slide, the server checks the quote letter by letter, and the quote is written into the card so you can read it next to the answer.

**What it proves:** the quote is on the slide, and the answer is inside the quote.
**What it does not prove:** that the card is correct. You still need to read your cards.

## Quick start

```bash
pip install slide-anki-mcp
claude mcp add slide-anki -- slide-anki-mcp
```

Then ask Claude: "Read C:\lectures\renal.pdf with slide-anki. Make cards from slides 3 to 10, quote each slide in the evidence field, and export to C:\lectures\renal.tsv." Give the full path to the PDF. It reads PDF only: for a PowerPoint deck, use File → Save As → PDF first (tried once with PowerPoint on a 31-slide deck, all slides had text). Import the `.tsv` in Anki with File → Import.

Needs Python 3.10 or newer. Also on PyPI: https://pypi.org/project/slide-anki-mcp/

## Tools

| Tool | What it does |
|---|---|
| `list_slides(pdf_path)` | Slide numbers with first line and length. Warns about slides with little or no text |
| `get_slide(pdf_path, slide)` | Exact text of one slide, to copy quotes from |
| `check_cards(pdf_path, cards)` | Checks each card. A card whose quote fails comes back with the slide text so the quote can be fixed |
| `export_anki(pdf_path, cards, out_path)` | Writes a new `.tsv` only if every card passes. Each card is tagged `Slide_N`. Duplicates (same front and back, ignoring case and extra spaces) are written once |

A card is:

```json
{"front": "Where is ADH produced?", "back": "the hypothalamus",
 "evidence": "ADH is produced in the hypothalamus", "slide": 1}
```

A card passes only if all of these are true:

1. The slide has text. A slide with none is rejected with "slide has no text, cannot verify".
2. `evidence` is at least 4 words and is on the cited slide exactly as quoted. Case, extra spaces, a word split by a hyphen at a line break, and dash or quote style are ignored. Everything else must match, including `<`, `>`, `+`, `-` and numbers. Superscripts are kept: `10⁵` is not `105`.
3. `back` is inside `evidence`, and is not cut from a longer token: `1500 ml` is not found in `1000-1500 ml`, and `70 mV` is not found in `-70 mV`.

`export_anki` also refuses an `out_path` that does not end with `.tsv`, that already exists, or whose folder does not exist. It never overwrites a file.

## Example

Made with a small two-slide test PDF. Slide 1 says "ADH is produced in the hypothalamus", slide 2 says "Normal plasma sodium is 135-145 mmol/L". `check_cards` with one wrong card and one right card:

```json
[
  {"slide": 1, "ok": false, "unsupported": ["evidence is not on this slide exactly as quoted"]},
  {"slide": 2, "ok": true, "unsupported": []}
]
```

(The failing card also comes back with `slide_text`, left out here.) After fixing the first card and sending the sodium card twice by mistake, `export_anki` returns:

```json
{"written": "/path/to/cards.tsv", "count": 2, "duplicates_skipped": [2]}
```

and the file contains:

```
#separator:tab
#html:false
#tags column:3
"Where is ADH produced?"	"the hypothalamus  |  Source (slide 1): ADH is produced in the hypothalamus"	"slides Slide_1"
"Normal plasma sodium?"	"135-145 mmol/L  |  Source (slide 2): Normal plasma sodium is 135-145 mmol/L"	"slides Slide_2"
```

The header lines are read by Anki 2.1.54 and newer. Older versions need the field separator set to Tab by hand. Every field is quoted so a front that starts with `#` is not read as a header line. Tested with the import code of the official `anki` Python library (version 26.09.4), not the Anki desktop app: 3 of 3 test notes imported, the `#` front, the Arabic text and the tags came through. The file doubles quotes inside a field (standard CSV); Anki stored them as `&quot;`, which should show as plain quotes. I have not opened the result in the Anki app.

## Install for Claude Desktop

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

If Claude cannot find the command, put its full path in `"command"`. Get the path with `where slide-anki-mcp` on Windows or `which slide-anki-mcp` on macOS and Linux. If you installed inside a virtual environment, you need that full path for Claude Code as well.

## What it cannot catch

- **Meaning.** It checks that words are on the slide, not what they mean. If the slide says "Mitral valve does not have three cusps", a card with the back "three cusps" and that full sentence as evidence passes. The "does not" is in the exported card, so you can see it, but the server does not detect it.
- **Shortened answers.** A back that stops in the middle of a comma list is rejected (`GALT, GALK` from `GALT, GALK, GALE`). Other shortenings pass, and so does a true line from the slide under a question it does not answer, such as one enzyme from a list under "which enzyme is the classic one?".
- **Negation and direction.** If `not`, `no`, `without`, `↑` or `↓` stands right before the back inside the quote, the card is rejected unless the back includes it. Other wording that flips the meaning is not caught.
- **The front.** The question is never checked. A true sentence under the wrong question passes.
- **Units that differ only in case.** Case is ignored, so `mM` and `mm`, or `Mg` and `mg`, count as the same.
- **Quotes that start right after a dash or sign.** If a slide line reads `Beverages -1000-1500 ml`, the quote has to include the dash. A quote that cuts a number, unit or range in the middle (`135` from `135-145 mmol/L`, `500 ml` from `1,500 ml`, `80 mmHg` from `120/80 mmHg`) is rejected.
- **Paraphrases.** A correct answer in other words is rejected. Copy the slide's wording. Small differences such as "200mL" on the slide and "200 mL" in the card are also rejected.
- **Images.** Text inside pictures and diagrams is not read. Scanned pages with no text can be read by OCR on Windows only: `pip install slide-anki-mcp[ocr]` (uses the OCR built into Windows 10/11; Arabic needs the Arabic OCR language). Such slides are marked in `list_slides`, and their cards come back with `"ocr": true`. On two scanned test files and one scanned real Arabic Word document, 46 of 49 correct cards passed and 0 of 46 wrong ones; the misses were a misread `50%` and table rows. OCR runs only on pages with no text layer, so a picture on a slide that has some text is still not read. Without the extra, or on macOS and Linux, scanned slides are rejected. On one real 40-slide lecture, 4 slides had no text at all and 7 more had under 40 characters, mostly section titles.
- **Glued words.** When a PDF glues two text boxes (`GlycerolConsequence`), a quote that starts at the second box is still accepted. Glue between two lowercase letters or capitals only is not split.
- **Unreadable characters.** A character the PDF cannot map (`�`) matches a minus sign only, because that is what it was on the lecture I tested. `list_slides` warns about such slides. A slide that really has another symbol there could let a quote with `-` pass.
- **Bad text extraction.** If the PDF stores text in an odd way, the extracted words can be split or out of order, and correct cards will fail.

On a second real lecture (a 31-slide PowerPoint saved as PDF), I wrote 40 correct and 40 wrong cards by hand: all 40 correct cards were accepted (one only after the glued-words fix), and 4 of 40 wrong cards were accepted, all of them true lines under the wrong question or a shortened quote. Small sample, written by me, so treat it as a rough guide.

For the numbers: an earlier version of this tool matched the answer against the slide with symbols removed. On a real 40-slide lecture it accepted 8 of 30 cards that were made wrong on purpose, for example a changed number or a dropped "No". This version keeps symbols and requires a quote. On a new set of 30 correct and 29 wrong cards from the same lecture (written by a reviewer, so a small and friendly sample), it accepted 26 of the 30 correct cards and 0 of the 29 wrong ones. The 4 rejected correct cards were quotes shorter than 4 words, a quote with `and` where the slide has `&`, and a quote that left out a leading dash. The wrong cards did not include a dropped "not", because that lecture has no usable place for one, so that case is untested on real slides.

### Arabic

Tested on 5 Arabic PDFs from 4 producers: PowerPoint, Word (a generated file and a real document), Edge and Chrome. Each producer breaks Arabic text differently, and the tool puts it back: Word glues words without spaces and flips Arabic-Indic numbers, Edge and Chrome store letters in presentation forms in visual order, PowerPoint loses spaces next to numbers and units. For quotes that contain Arabic, spaces and punctuation are ignored, but every letter, digit and sign (`% + - / < > = ± ≤ ≥ °`) must match in order, and negation words (`لا ليس لم لن غير بدون`) must be in the back like `not` in English.

On those files, 86 of 86 correct Arabic cards were accepted and 0 of 81 wrong cards (changed number, unit or word, swapped numbers, dropped `لا`, reversed digits, a cut range). The cards were written by a reviewer from the source text, so this is a small, friendly sample.

Known trade-offs and gaps:

- Ignoring spaces and punctuation means a merged or split Arabic word, or a missing `« » . : ؟`, still passes.
- Word drops `-` and `/` between numbers. On a slide with neither between numbers, `١٢٠/٨٠`, `١٢٠-٨٠` and `١٢٠ ٨٠` count as the same.
- Reversed Arabic-Indic numbers in Word are detected from one signal (a backwards number starting with ٠ somewhere in the file). Without it, those numbers are not flipped.
- A scanned PDF (pages that are only pictures) is rejected on every card with "slide has no text, cannot verify"; tested on a real lecture rendered to images. It is not read.
- Fails: an Arabic PDF made with PyMuPDF (MuPDF) HTML. Its text layer holds letters in reversed visual order and some wrong characters, so exact quotes fail. `list_slides` now warns when a text layer looks damaged like this; only text copied from `get_slide` would match.
- Not tested: Google Docs or Slides export, LibreOffice, macOS (Preview, Pages, Keynote).

## Roadmap

These are real gaps, not promises:

- **OCR on macOS and Linux.** It works on Windows only for now.
- **Meaning-aware checking**, so a correct paraphrase can pass and a phrase taken out of context can be caught.
- **Testing on more real Arabic lectures (Word, PowerPoint, scans) and a real Anki import.**

## Develop

```bash
pip install -e ".[test]"
pytest
python tests/e2e_stdio.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

MIT licensed.
