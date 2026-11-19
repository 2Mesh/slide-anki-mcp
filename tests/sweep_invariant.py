"""Run: python tests/sweep_invariant.py FOLDER_WITH_PDFS. For every slide line of 4+ words, try
several backs (word spans). Every card the tool calls 'verified' must rebuild the slide's own line
when the blank is filled, and the tool must never raise. Prints counts only."""
import random, re, sys
from pathlib import Path
from slide_anki_mcp import core

rng, tried, verified, bad = random.Random(1), 0, 0, []
for pdf in sorted(Path(sys.argv[1]).glob("*.pdf")):
    try:
        slides = core.read_slides(str(pdf))
    except Exception:
        continue
    for n, text in enumerate(slides, 1):
        for line in {" ".join(l.split()) for l in text.splitlines()}:
            words = line.split()
            if len(words) < 4:
                continue
            for _ in range(3):
                i = rng.randrange(len(words)); j = min(len(words), i + rng.randint(1, 3))
                back = " ".join(words[i:j]); tried += 1
                r = core.check_card({"cloze": True, "back": back, "slide": n, "evidence": line}, slides)
                if r.get("status") == "verified":
                    verified += 1
                    pua = lambda t: re.sub("[-]", "•", t)  # private-use bullets are shown as dots
                    filled = pua(r["front"].replace("___", back))
                    if pua(line) not in filled or r["front"].count("___") < 1:
                        bad.append((pdf.name[:3], n, back))
print(f"tried {tried}, verified {verified}, violations {len(bad)}")
sys.exit(1 if bad else 0)
