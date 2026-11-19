# Contributing

Thank you for helping. This is a small project and I want to keep it small: it reads slide text, checks cards against it, and writes an Anki file. Changes that keep it simple are the easiest to accept.

## Run the tests

```bash
pip install -e ".[test]"
pytest
python tests/e2e_stdio.py
```

`pytest` runs the unit tests in `tests/test_core.py`. The test PDFs are made by the tests with `reportlab`, so you do not need any lecture files. The Arabic test needs a font with Arabic letters (Arial or Tahoma on Windows, DejaVu Sans on Linux). If none is found, it is skipped.

`tests/e2e_stdio.py` starts the server the way Claude does (over stdio) and calls `export_anki` three times: with a good card, with a bad card (nothing may be written), and with a path that already exists (it must be refused).

GitHub Actions runs both on Python 3.10 and 3.12, on Ubuntu and Windows.

## Where things are

- `src/slide_anki_mcp/core.py`: reading the PDF, checking a card, writing the `.tsv`. No MCP code here.
- `src/slide_anki_mcp/server.py`: the four MCP tools. Each one is a thin wrapper around `core.py`.

## Adding a check

1. Write a test in `tests/test_core.py` that builds a small PDF with `make_pdf`, makes a card that should fail (or pass), and asserts the result of `core.check_card`.
2. Run `pytest` and see the new test fail.
3. Change `check_card` in `core.py`. A failing card should set `ok` to `False` and add a short, readable reason or the failing text to `unsupported`.
4. Run all the tests again. Existing tests should keep passing unless the change is on purpose; if so, say why in the pull request.

## Please keep in mind

- Do not add real lecture PDFs to the repository. They belong to the lecturer.
- Add a new dependency only if the change really needs it.
- Keep the README honest: only describe what the code does and what you have tested.
