# slide-anki-mcp

[![tests](https://github.com/2Mesh/slide-anki-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/2Mesh/slide-anki-mcp/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/slide-anki-mcp)](https://pypi.org/project/slide-anki-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Turn your lecture slides into Anki cards that always match the slide.**

An MCP server for students. Claude reads your lecture PDF, and every card it makes comes with a quote from the slide. The server checks that quote letter by letter, builds the question from the slide's own sentence, and writes an Anki file where each answer shows its source.

```
Slide 7:  "ADH is produced in the hypothalamus"
Card:     ADH is produced in ___            ->  the hypothalamus
Source:   slide 7, quoted next to the answer
```

## Why you will like it

- **Cards that follow your lecturer.** Exams are graded against the slides, so the cards come from the slides.
- **Fill-in-the-blank cards built for you.** The question is the slide's own sentence with the answer hidden. Fill the blank and you get the slide line back, letter for letter. This was checked on 335,175 generated cards over 271 PDFs.
- **Every answer shows its source.** The slide number and the quote are written into the card.
- **English and Arabic.** Works with Arabic slides saved from Word, PowerPoint, Edge and Chrome, including numbers, units and mixed Arabic and English lines.
- **Scanned slides.** Optional OCR on Windows reads pages that are only pictures.
- **Phone page.** A small page in `docs/app` lets you pick a PDF in your phone browser, select the answer, and download a file for Anki. The PDF never leaves your phone.
- **Private.** Everything runs on your computer. No account and no API key.

## Quick start

```bash
pip install slide-anki-mcp
claude mcp add slide-anki -- slide-anki-mcp
```

Then ask Claude:

> Read C:\lectures\renal.pdf with slide-anki. Make cloze cards from slides 3 to 10 and export them to C:\lectures\renal.tsv.

Open Anki and choose **File → Import**. Needs Python 3.10 or newer. For a PowerPoint deck, use **File → Save As → PDF** first.

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

If Claude cannot find the command, put its full path in `"command"` (`where slide-anki-mcp` on Windows, `which slide-anki-mcp` on macOS and Linux).

## The tools

| Tool | What it does |
|---|---|
| `list_slides(pdf_path)` | Lists the slides with their first line and size |
| `get_slide(pdf_path, slide)` | Gives the exact text of one slide |
| `check_cards(pdf_path, cards)` | Checks each card and says what to fix. For a cloze card it returns the finished question |
| `export_anki(pdf_path, cards, out_path)` | Writes a new `.tsv` for Anki, tagged by slide. Cloze cards are written directly |

A cloze card needs only the answer, the slide number and the quote:

```json
{"cloze": true, "back": "the hypothalamus",
 "evidence": "ADH is produced in the hypothalamus", "slide": 7}
```

The tool answers with the question already built:

```json
{"ok": true, "status": "verified", "front": "ADH is produced in ___"}
```

You can also write your own question. Read it next to its quote, then list the card's number in `reviewed_indexes`. It is exported with the Anki tag `reviewed`.

## What you get in Anki

```
"ADH is produced in ___"    "the hypothalamus  |  Source (slide 7): ADH is produced in the hypothalamus"    "slides Slide_7"
```

Each card carries its slide tag, so you can filter by lecture and slide. The file imports into Anki 2.1.54 and newer. Import was tested with the official `anki` Python library.

## Good to know

- **Cloze cards verify the text.** The checker confirms that the slide line is rebuilt exactly. Choose an answer that leaves enough of the sentence to make a clear question; the tool tells you when a blank has too little context and suggests the exact slide line.
- **Your own questions are welcome.** The tool shows you the question beside its quote so you confirm it in one step.
- **Best with text PDFs.** Slides saved as PDF from Word, PowerPoint, Edge or Chrome work well. Scanned pages work on Windows with `pip install "slide-anki-mcp[ocr]"` (Arabic needs the Arabic OCR language from Windows).
- **Arabic from Edge or Chrome** is read by the desktop tool. The phone page reads Arabic from Word and PowerPoint.
- **Full test results** with every number and limit are in [docs/TESTING.md](docs/TESTING.md).

## Feedback so far

Informal, by message, not measured: two classmates tried it on their own lectures and said it worked well. I have no written test results yet. If you try it, please open a "Test report" issue, including when it fails.

## Develop

```bash
pip install -e ".[test]"
pytest
python tests/e2e_stdio.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
