# Issues to open

Three issue texts, ready to paste into GitHub. Not filed yet.

---

## 1. Read text from image slides (OCR)

**Problem**

Many lecture slides are pictures: diagrams, screenshots, scanned pages. `pypdf` only reads real text, so these slides come out empty. On one real 40-slide lecture, 4 slides had no text at all and 7 more had under 40 characters. `list_slides` warns about them, and cards that cite a slide with no text are rejected with "slide has no text, cannot verify".

**What would help**

An optional OCR step for slides with little or no text, so their words can be used in the check.

**Things to decide**

- Which OCR tool. It should run offline and install without too much trouble on Windows.
- OCR makes mistakes. A card should not fail only because OCR misread a letter, and it should not pass because of an OCR error either. The result could say which text came from OCR.
- It should stay optional, so the basic install stays small.

**Done when**

A test PDF with text drawn as an image gives that text through `get_slide`, and a card that quotes it passes `check_cards`.

---

## 2. Accept correct paraphrases (meaning-aware matching)

**Problem**

The check needs the model to quote the slide: an `evidence` quote must be on the slide exactly (symbols and numbers kept) and the answer must be inside it. A correct answer in different words is rejected, so the model has to copy the slide's wording. The check also cannot see meaning: if the slide says "Furosemide does not cause hyperkalemia", the back "cause hyperkalemia" with that full sentence as evidence passes, and only a person reading the exported evidence can see the "does not".

**What would help**

A way to accept answers that mean the same as the slide, and to catch answers that take slide words out of context.

**Things to decide**

- How to do it without letting invented facts back in, which is the reason this project exists. Any looser match should still show which slide text supports the answer.
- Whether this needs a model, and if so, whether it can run locally.
- Keep the strict check as the default, with the looser one as an option.

**Done when**

There are tests for: a correct paraphrase that passes, a wrong answer with similar words that fails, and the furosemide example above that fails.

---

## 3. Test with real Arabic slides

**Problem**

Arabic matching works on a test PDF made with `reportlab`, `arabic-reshaper` and `python-bidi`. It has not been tried on a real Arabic lecture exported from PowerPoint, Word or Google Slides. Those programs may store Arabic text differently. If the text comes out in reversed order, correct Arabic cards will fail.

**What would help**

- Try a few real Arabic or mixed Arabic/English lecture PDFs and note whether `get_slide` returns the Arabic in the right order.
- If some programs give reversed text, find a way to detect and fix it, with a test.

**Please do not** attach lecture PDFs you do not have the right to share. A small PDF you made yourself, exported from the same program, is enough.

**Done when**

The README says which PDF sources were tested with Arabic, and there is a test for each case that needed a fix.
