"""End-to-end: spawn the server over stdio and call the tools like Claude would."""
import asyncio
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
    params = StdioServerParameters(command=sys.executable, args=["-m", "slide_anki_mcp.server"], env={**__import__("os").environ})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            good = [{"front": "How many cusps?", "back": "The mitral valve has two cusps", "slide": 1}]
            bad = [{"front": "How many cusps?", "back": "The mitral valve has three big cusps", "slide": 1}]
            ok = await s.call_tool("export_anki", {"pdf_path": str(pdf), "cards": good, "out_path": str(d / "o.tsv")})
            no = await s.call_tool("export_anki", {"pdf_path": str(pdf), "cards": bad, "out_path": str(d / "p.tsv")})
            print("GOOD:", ok.content[0].text[:120])
            print("BAD :", no.content[0].text[:160])
            assert (d / "o.tsv").exists() and not (d / "p.tsv").exists()
            print("E2E OK")


asyncio.run(main())
