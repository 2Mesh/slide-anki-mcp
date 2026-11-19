"""Pure logic: read slides from a PDF, check cards against them, write Anki TSV.

The check is an evidence check. Every card must carry ``evidence``: a quote
copied from the cited slide. The server confirms the quote is really on that
slide (symbols, signs and numbers kept exactly) and that the answer sits inside
the quote. It cannot tell whether the card means what the slide means: the
quote is written into the exported card so the student can read it.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfReader

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MIN_TEXT_CHARS = 40  # list_slides warns below this
MIN_WORD_CHARS = 5  # fewer word characters than this = "no text"
MIN_EVIDENCE_WORDS = 4

_SUPER = str.maketrans({
    "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4", "⁵": "^5", "⁶": "^6",
    "⁷": "^7", "⁸": "^8", "⁹": "^9", "⁺": "^+", "⁻": "^-", "ⁿ": "^n", "�": "-",
    "₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4", "₅": "_5", "₆": "_6",
    "₇": "_7", "₈": "_8", "₉": "_9",
    "–": "-", "—": "-", "−": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
})

_ARABIC = str.maketrans({"ی": "ي", "ى": "ي", "ھ": "ه", "ک": "ك", "ـ": "", "​": " "})


def _text(s: str, join_hyphen: bool = True, split_joined: bool = False) -> str:
    """Make text comparable without losing symbols, signs or digits.

    Only layout is ignored: case, runs of whitespace, a word split by a hyphen
    at a line break, dash and quote styles. Superscripts become ^n so that
    "10⁵" never turns into "105". NFKC turns Arabic presentation forms (which
    PDFs may store) back into normal letters; Arabic short vowels are dropped.
    Persian-style yeh, heh and kaf, which some fonts produce, count as the
    Arabic ones, and a space is added where Arabic meets Latin or digits.
    """
    if split_joined:  # text boxes glued by the PDF: "GlycerolConsequence"
        s = re.sub(r"(?<=[a-z]{4})(?=[A-Z])", " ", s)
    s = s.translate(_SUPER)
    s = unicodedata.normalize("NFKC", s).translate(_ARABIC)
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Mn", "Cf"))
    s = re.sub(r"(?<=[^\W\d_])-[ \t]*\r?\n[ \t]*(?=[^\W\d_])", "" if join_hyphen else "-", s)
    s = re.sub(r"(?<=[؀-ۿ])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[؀-ۿ])", " ", s)
    return re.sub(r"\s+", " ", s).strip().casefold().strip(" .;:,")


_NEGATION = re.compile(r"(?:(?:^|[\s(\[])(?:not|no|never|without|non|cannot|neither|nor"
                       r"|لا|ليس|ليست|لم|لن|غير|بدون|دون)|n't|[↑↓])\s+$"
                       r"|(?:^|[\s(\[])(?:(?:increas|decreas|reduc|rais|elevat)(?:e|es|ed|ing)|inhibit(?:s|ed|ing)?|suppress(?:es|ed|ing)?|lower(?:s|ed|ing))\s+(?:the\s+|a\s+|an\s+)?$")
_MORE = re.compile(r"\s*(?:,\s*(?!etc\b|e\.g\b|i\.e\b)|\s(?:&|and|or)\s+)\S")


def _matches(haystack: str, needle: str) -> list:
    """All matches of needle in haystack as whole words, not cut from a longer token.

    "1500 ml" is not found in "1000-1500 ml", "70 mv" is not found in "-70 mv",
    and "↑" is not found in "↑↑".
    """
    if not needle:
        return []
    pattern = r"(?<![\w.+\-<>^↑↓×])(?<!\d[,/:])" + re.escape(needle) + r"(?![\w^+\-/%↑↓×]|[.,:]\d)"
    return list(re.finditer(pattern, haystack))


def _contains(haystack: str, needle: str) -> bool:
    return bool(_matches(haystack, needle))


# ---- Arabic PDFs ------------------------------------------------------------
_AR = "\u0600-\u06FF"
_PRESENTATION_FORMS = re.compile("[\uFB50-\uFDFF\uFE70-\uFEFF]")  # Chromium (Edge, Chrome) prints these
_INDIC_RUN = re.compile("[\u0660-\u0669]+")
_JOINABLE = re.compile(f"[{_AR}0-9]")
_UNITS = re.compile(rf"(?:[^A-Za-z0-9{_AR}\s][^A-Za-z0-9{_AR}]*)?[{_AR}](?:[^A-Za-z0-9]*[{_AR}])*[^A-Za-z0-9{_AR}]*"
                    r"|[A-Za-z][A-Za-z0-9/+().'-]*(?: +[A-Za-z(][A-Za-z0-9/+().'-]*)*|\d+(?:[.,/:]\d+)*|\S")


def _page_chunks(page) -> list:
    chunks: list = []
    page.extract_text(visitor_text=lambda text, *_: chunks.append(text) if text else None)
    return chunks


def _join_chunks(chunks: list, flip_indic: bool) -> str:
    """Join pypdf's text pieces. Word writes each Arabic word as its own piece with
    no space glyph, and can write Arabic-Indic numbers backwards ("٠٣" for "٣٠")."""
    out, arabic = "", any(re.search(f"[{_AR}]", c) for c in chunks)
    for text in chunks:
        core = text.strip()
        if flip_indic and _INDIC_RUN.fullmatch(core):
            text = text.replace(core, core[::-1])
        if out and (_JOINABLE.match(out[-1]) and _JOINABLE.match(text[0])
                    or arabic and out[-1].isdigit() and text[0].isascii() and text[0].isalpha()):
            out += " "  # PowerPoint glues a list number to the next piece: ".3ADH"
        out += text
    return out


def _visual_to_logical(line: str) -> str:
    """Chromium writes a right-to-left line from left to right: its Arabic, English
    and number pieces come in reverse order ("mmol/L 145-135 الصوديوم"). Reverse them."""
    if not re.search(f"[{_AR}]", line) or not re.search("[A-Za-z0-9]", line):
        return line
    units = [u.strip() for u in _UNITS.findall(line)][::-1]
    out = ""
    for i, u in enumerate(units):
        glue = (u in ("-", "+") and i and units[i - 1][-1:].isdigit()) or (out[-1:] in ("-", "+") and u[:1].isdigit())
        out += u if not out or glue else " " + u
    return out


def _reorder(slide: str) -> str:
    return "\n".join(_visual_to_logical(line) for line in slide.splitlines())


def _loose_words(t: str, drop_number_signs: bool) -> list:
    t = re.sub(r"(?<!\d)[.,]|[.,](?!\d)|[^\w\s%+<>=^↑↓×±≤≥°/.,-]", " ", t)  # punctuation PDFs lose
    if drop_number_signs:  # Word can lose the "-" or "/" between two numbers
        t = re.sub(r"(?<=\d)\s*[-/]\s*(?=\d)", " ", t)
    return t.split()


def _loose_join(words: list) -> str:
    out = ""
    for w in words:
        out += ("|" if out[-1:].isdigit() and w[:1].isdigit() else "") + w
    return out


def _arabic_loose_match(slide_t: str, ev_t: str) -> bool:
    """For an Arabic quote: ignore spaces and punctuation, keep every letter, digit
    and sign in order. The quote must start and end where a slide word starts and ends."""
    drop = not re.search(r"\d\s*[-/]\s*\d", slide_t)
    words, target = _loose_words(slide_t, drop), _loose_join(_loose_words(ev_t, drop))
    for i in range(len(words)):
        for j in range(i, len(words)):
            acc = _loose_join(words[i:j + 1])
            if acc == target:
                return True
            if not target.startswith(acc):
                break
    return False


_OCR_CACHE: dict = {}


class OcrText(str):
    """Slide text read by OCR from a picture, not from the PDF's text layer."""
    ocr = True


def _ocr_rtl(line: str) -> str:
    """Windows OCR gives an Arabic line's words in visual (left-to-right) order and
    numbers such as 145-135 or 80/120 the same way. Put them in reading order."""
    if not re.search(f"[{_AR}]", line):
        return line
    groups: list = []
    for word in line.split():
        m = re.fullmatch(r"(\d+(?:\.\d+)?)([-/])(\d+(?:\.\d+)?)", word)
        word = f"{m[3]}{m[2]}{m[1]}" if m else word
        if groups and re.match("[A-Za-z]", word) and re.match("[A-Za-z]", groups[-1][-1]):
            groups[-1].append(word)  # an English phrase keeps its own order
        else:
            groups.append([word])
    return " ".join(" ".join(g) for g in reversed(groups))


def _ocr_rtl_rows(lines: list) -> list:
    """Windows OCR can cut one Arabic line in two and list the parts out of order.
    Join parts that share a baseline and sit close together, right part first."""
    segs = []
    for ln in lines:
        boxes = [w["bounding_rect"] for w in ln["words"]]
        if not boxes:
            continue
        x0, x1 = min(b["x"] for b in boxes), max(b["x"] + b["width"] for b in boxes)
        y0, y1 = min(b["y"] for b in boxes), max(b["y"] + b["height"] for b in boxes)
        segs.append((x0, x1, (y0 + y1) / 2, y1 - y0, ln["text"]))
    rows: list = []
    for seg in sorted(segs, key=lambda g: g[2]):
        for row in rows:
            if any(abs(seg[2] - o[2]) < 0.5 * max(seg[3], o[3])
                   and max(seg[0] - o[1], o[0] - seg[1]) < 3 * max(seg[3], o[3]) for o in row):
                row.append(seg)
                break
        else:
            rows.append([seg])
    return [" ".join(_ocr_rtl(g[4]) for g in sorted(row, key=lambda g: -g[1])) for row in rows]


def _ocr_page(page) -> str:
    """Text of the pictures on a page, by Windows OCR. Empty when the optional
    extra is not installed (pip install slide-anki-mcp[ocr]) or OCR fails."""
    try:
        import winocr
    except ImportError:
        return ""
    lines: list = []
    for image in page.images:
        try:
            img = image.image.convert("RGB")
            if img.width < 200 or img.height < 100:
                continue
            found = {}
            for lang in ("en", "ar"):
                try:
                    with ThreadPoolExecutor(1) as pool:  # winocr calls asyncio.run: not inside the server's loop
                        found[lang] = pool.submit(winocr.recognize_pil_sync, img, lang).result()["lines"]
                except Exception:  # that OCR language is not installed in Windows
                    found[lang] = []
        except Exception:
            continue
        ar = " ".join(ln["text"] for ln in found["ar"])
        letters = len(re.findall(r"[^\W\d_]", ar))
        if letters and len(re.findall(f"[{_AR}]", ar)) > 0.3 * letters:
            lines += _ocr_rtl_rows(found["ar"])
        else:
            lines += [ln["text"] for ln in found["en"]]
    return "\n".join(lines)


def read_slides(pdf_path: str) -> list[str]:
    """Return the text of each page (slide), index 0 = slide 1.

    A page with no text layer is read by OCR when the optional extra is
    installed; its text is an ``OcrText`` so callers can warn about it."""
    if Path(pdf_path).is_dir():
        raise ValueError(f"{pdf_path} is a folder: give the full path of the PDF file")
    try:
        reader = PdfReader(pdf_path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError(f"{pdf_path} is password-protected: remove the password and save a copy")
        pages = list(reader.pages)
    except ValueError:
        raise
    except FileNotFoundError:
        raise ValueError(f"file not found: {pdf_path}") from None
    except Exception as exc:  # pypdf raises several error types for bad files
        raise ValueError(f"cannot read {pdf_path} as a PDF: {exc}") from None
    if not pages:
        raise ValueError("PDF has no pages")
    chunks = [_page_chunks(page) for page in pages]
    flip = any(_INDIC_RUN.fullmatch(c.strip()) and len(c.strip()) > 1 and c.strip()[0] == "\u0660"
               for page in chunks for c in page)  # a number starting with ٠: written backwards
    # a NUL character in a lecture PDF is the degree sign (a Symbol font glyph): "60 \x00C" is "60 °C"
    texts = [_join_chunks(c, flip).replace("\x00", "°").strip() for c in chunks]
    texts = [_reorder(t) if _PRESENTATION_FORMS.search(t) else t for t in texts]
    stat = Path(pdf_path).stat()
    for i, page in enumerate(pages):
        if not _has_text(texts[i]):
            key = (str(Path(pdf_path).resolve()), stat.st_mtime_ns, stat.st_size, i)
            ocr = _OCR_CACHE.get(key) or _ocr_page(page)  # every tool call reads the PDF again; OCR is slow
            if ocr:
                _OCR_CACHE[key] = ocr
                texts[i] = OcrText(ocr)
    return texts


def _looks_damaged(text: str) -> bool:
    """Control characters, or Latin Extended-B letters on an Arabic page (such as
    U+01C4 in a MuPDF Arabic PDF), mean the PDF maps its glyphs to wrong letters."""
    bad = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    if re.search(f"[{_AR}]", text) or _PRESENTATION_FORMS.search(text):
        bad += len(re.findall("[\u0180-\u024F]", text))
    return bad >= 3


def _has_text(slide: str) -> bool:
    return len(re.findall(r"\w", slide)) >= MIN_WORD_CHARS


def slide_overview(slides: list[str]) -> list[dict]:
    out = []
    for i, text in enumerate(slides, start=1):
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        warning = None
        if not _has_text(text):
            warning = "slide has no text, cannot verify cards against it"
        elif getattr(text, "ocr", False):
            warning = "text read by OCR from a picture: OCR can misread letters, check each quote against the slide"
        elif _looks_damaged(text):
            warning = "text layer looks damaged (wrong or reversed letters): copy quotes from get_slide and check them"
        elif "�" in text:
            warning = f"{text.count(chr(0xFFFD))} unreadable character(s) shown as �; they match '-' only"
        elif len(text) < MIN_TEXT_CHARS:
            warning = "under 40 characters of text: may be an image or title slide"
        out.append({"slide": i, "title": first[:80], "chars": len(text), "warning": warning})
    return out


def _fail(result: dict, *problems: str) -> dict:
    result["ok"] = False
    result["unsupported"].extend(problems)
    return result


def check_card(card: dict, slides: list[str]) -> dict:
    """Check one card {front, back, slide, evidence}. Never raises on bad input.

    Passes only if: the slide has text; the evidence is a quote of at least
    4 words that is literally on the cited slide; and the back is inside the
    evidence. Returns ``ok`` and ``unsupported`` (the reasons). When a card
    fails, the slide text is returned too so the model can quote it correctly.
    """
    result = {"slide": None, "ok": True, "unsupported": []}
    if not isinstance(card, dict):
        return _fail(result, "card must be an object with front, back, slide, evidence")
    page = card.get("slide")
    result["slide"] = page
    if isinstance(page, bool) or not isinstance(page, int):
        return _fail(result, "slide must be a whole number such as 3")
    if not 1 <= page <= len(slides):
        return _fail(result, f"slide number out of range: this PDF has slides 1 to {len(slides)}")
    slide = slides[page - 1]
    front, back, evidence = card.get("front"), card.get("back"), card.get("evidence")
    for name, value in (("front", front), ("back", back), ("evidence", evidence)):
        if not isinstance(value, str) or not _text(value):
            _fail(result, f"{name} must be non-empty text")
    if result["unsupported"]:
        result["slide_text"] = slide[:3000]
        return result
    if not _has_text(slide):
        return _fail(result, "slide has no text, cannot verify")
    slide_t, ev_t, back_t = _text(slide), _text(evidence), _text(back)
    if len(ev_t.split()) < MIN_EVIDENCE_WORDS:
        _fail(result, f"evidence too short: quote a full sentence or line (at least {MIN_EVIDENCE_WORDS} words)")
    elif not (any(_contains(_text(slide, join_hyphen=j, split_joined=sp), ev_t)
                  for j, sp in ((True, False), (False, False), (True, True)))
              or (_PRESENTATION_FORMS.search(slide) and _contains(_text(_reorder(slide)), ev_t))
              or (re.search(f"[{_AR}]", ev_t)
                  and _arabic_loose_match(_text(slide.replace("\u2014", " ")), _text(evidence.replace("\u2014", " "))))):
        _fail(result, "evidence is not on this slide exactly as quoted")
    elif not (hits := _matches(ev_t, back_t)):
        _fail(result, "the back is not inside the evidence quote")
    elif "," in back_t and all(_MORE.match(ev_t, h.end()) for h in hits):
        _fail(result, "the back stops in the middle of a list: the evidence goes on with more items, include them all")
    elif any(_NEGATION.search(ev_t[: h.start()]) for h in hits):
        _fail(result, "the evidence has not/no/without or an arrow just before the back: include it in the back, because it changes the meaning")
    if getattr(slide, "ocr", False):
        result["ocr"] = True  # the quote matched OCR text, which can be misread
    if not result["ok"]:
        result["slide_text"] = slide[:3000]
    return result


def card_key(card: dict) -> tuple[str, str]:
    return _text(card["front"]), _text(card["back"])


def write_anki_tsv(cards: list[dict], out_path: str, deck_tag: str = "slides") -> str:
    """Write an Anki-importable tab-separated file: Front, Back, Tags.

    The back ends with the slide number and the evidence quote, so the student
    sees the source beside every answer. Every field is quoted, so a front that
    starts with '#' is not read as a header line. The header lines tell Anki
    2.1.54+ the separator, plain text and tags column. Refuses any path that is
    not a new ``.tsv`` file in an existing folder.
    """
    path = Path(out_path)
    if not path.name.lower().endswith(".tsv"):
        raise ValueError("out_path must end with .tsv")
    if path.stem.split(".")[0].upper() in _RESERVED:
        raise ValueError(f"{path.name} is a reserved Windows name, choose another file name")
    if not path.parent.is_dir():
        what = "a file, not a folder" if path.parent.exists() else "a folder that does not exist"
        raise ValueError(f"{path.parent} is {what}")
    if path.is_dir():
        raise ValueError(f"a folder with that name already exists: {path}")
    try:
        fh = path.open("x", newline="", encoding="utf-8")
    except FileExistsError:
        raise ValueError(f"file already exists, choose a new name: {path}") from None
    except OSError as exc:  # for example a folder with that name, or no permission
        raise ValueError(f"cannot create {path}: {exc.strerror or exc}") from None
    with fh:
        fh.write("#separator:tab\n#html:false\n#tags column:3\n")
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_ALL)
        for card in cards:
            evidence = " ".join(card["evidence"].split())
            back = f"{card['back']}  |  Source (slide {card['slide']}): {evidence}"
            writer.writerow([card["front"], back, f"{deck_tag} Slide_{card['slide']}"])
    return str(path.resolve())
