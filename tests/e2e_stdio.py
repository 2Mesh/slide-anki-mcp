"""End-to-end: spawn the server over stdio and call the tools like Claude would."""
import asyncio
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from reportlab.pdfgen import canvas


async def main():
    d = Path(tempfile.mkdtemp())
    pdf = d / "lec.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 800, "Mitral valve")
    c.drawString(72, 780, "The mitral valve has two cusps")
    c.showPage()
    c.save()
    params = StdioServerParameters(command=sys.executable, args=["-m", "slide_anki_mcp.server"],
                                   env={**os.environ})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = sorted(t.name for t in (await s.list_tools()).tools)
            assert tools == ["check_cards", "export_anki", "get_slide", "list_slides"], tools
            ev = "The mitral valve has two cusps"
            good = [{"front": "How many cusps?", "back": "two cusps", "evidence": ev, "slide": 1}]
            bad = [{"front": "How many cusps?", "back": "three big cusps",
                    "evidence": "The mitral valve has three big cusps", "slide": 1}]

            async def export(cards, name):
                res = await s.call_tool("export_anki", {"pdf_path": str(pdf), "cards": cards,
                                                        "out_path": str(d / name)})
                return res

            ok = json.loads((await export(good, "o.tsv")).content[0].text)
            no = json.loads((await export(bad, "p.tsv")).content[0].text)
            again = await export(good, "o.tsv")
            print("GOOD :", ok["count"], "card written")
            print("BAD  :", no["rejected_card_indexes"], no["details"][0]["unsupported"])
            print("AGAIN:", again.isError, again.content[0].text[:80])
            assert (d / "o.tsv").exists() and not (d / "p.tsv").exists()
            assert again.isError  # an existing file is never overwritten
            body = [ln for ln in (d / "o.tsv").read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
            row = next(csv.reader(body, delimiter="\t"))
            assert row[0] == "How many cusps?" and ev in row[1] and row[2] == "slides Slide_1", row
            print("E2E OK")


asyncio.run(main())
