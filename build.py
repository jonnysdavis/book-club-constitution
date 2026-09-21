#!/usr/bin/env python3
"""Build the Book Club Constitution site from the club's Google Doc text.

Modes:
  python3 build.py --build REPO_DIR        regenerate index.html from REPO_DIR/source.txt
  python3 build.py --fetch DOC_URL REPO    fetch doc text export, build if changed (public docs)
The doc is the single source of truth; this file only formats it.
"""
import html, os, re, sys, urllib.request

CSS = """:root{--paper:#f6f1e7;--card:#fffdf8;--ink:#2a251d;--muted:#6f6557;--line:#e3d9c6;--accent:#8c2f2f;--accent-soft:#f2e2e0}
@media (prefers-color-scheme: dark){:root{--paper:#161310;--card:#221d16;--ink:#ece5d8;--muted:#a89e8d;--line:#3a332a;--accent:#d98b7f;--accent-soft:#37282442}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.65 Georgia,"Iowan Old Style","Times New Roman",serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.skip{position:absolute;left:-999px}
.skip:focus{left:1rem;top:1rem;background:var(--accent);color:#fff;padding:.4rem .7rem;border-radius:6px;z-index:10;text-decoration:none}
.layout{max-width:1080px;margin:0 auto;padding:2.75rem 1.25rem 4rem;display:grid;grid-template-columns:236px minmax(0,1fr);gap:2.75rem;align-items:start}
.toc{position:sticky;top:1.5rem;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.15rem}
.toc h2{margin:0 0 .6rem;font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-family:system-ui,sans-serif}
.toc ol{list-style:none;margin:0;padding:0;font-size:.93rem}
.toc a{display:flex;gap:.55rem;padding:.26rem .45rem;border-radius:7px;color:var(--ink);text-decoration:none}
.toc a:hover{background:var(--accent-soft)}
.toc .n{color:var(--accent);min-width:1.3em;font-variant-numeric:tabular-nums}
.print-btn{margin-top:1rem;width:100%;font:600 .85rem system-ui,sans-serif;color:var(--muted);background:none;border:1px solid var(--line);border-radius:8px;padding:.5rem;cursor:pointer}
.print-btn:hover{color:var(--accent);border-color:var(--accent)}
.doc-head h1{font-size:2.15rem;line-height:1.18;margin:.15rem 0 .35rem}
.preamble{color:var(--muted);font-style:italic;margin:.2rem 0 2.1rem}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.55rem 1.8rem;margin:0 0 1.35rem;scroll-margin-top:1.25rem}
h2{display:flex;align-items:baseline;gap:.65rem;margin:0 0 1rem;font-size:1.3rem;font-weight:700}
.art-no{color:var(--accent);font-size:.82rem;letter-spacing:.1em;text-transform:uppercase;white-space:nowrap;font-family:system-ui,sans-serif;font-weight:600}
h3{margin:1.2rem 0 .3rem;font-size:1.03rem}
.sec{color:var(--muted);margin-right:.4rem}
p{margin:.35rem 0}
ul{margin:.35rem 0;padding-left:1.4rem}
li{margin:.28rem 0}
.timeline{list-style:none;counter-reset:t;margin:.6rem 0 0;padding:0}
.timeline li{counter-increment:t;position:relative;padding:0 0 1.05rem 2.5rem}
.timeline li::before{content:counter(t);position:absolute;left:0;top:.02rem;width:1.65rem;height:1.65rem;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:.82rem;font-family:system-ui,sans-serif;font-weight:600}
.timeline li:not(:last-child)::after{content:"";position:absolute;left:.8rem;top:1.8rem;bottom:.15rem;width:2px;background:var(--line)}
.end{margin-top:2.4rem;text-align:center;color:var(--muted);font-style:italic}
.sync-note{margin-top:.6rem;text-align:center;color:var(--muted);font-size:.8rem;font-family:system-ui,sans-serif}
@media (max-width:920px){.layout{grid-template-columns:1fr;padding-top:1.75rem;gap:1.5rem}.toc{position:static}.toc ol{columns:2;column-gap:1rem}}
@media print{.toc,.print-btn,.skip,.sync-note{display:none}body{background:#fff;color:#000;font-size:11.5pt}.layout{display:block;max-width:none;padding:0}article{border:none;background:none;padding:0;break-inside:avoid;page-break-inside:avoid}}
"""

def esc(s): return html.escape(s, quote=False)

def titlecase(s):
    s = s.strip()
    return s.title() if s and s.upper() == s else s

ART_RE = re.compile(r"^Article\s+([IVXL]+)\s*[\u2014\u2013-]+\s*(.+)$", re.I)
SEC_RE = re.compile(r"^Section\s+(\d+)\.\s*(.*)$", re.I)
NAME_RE = re.compile(r"^([A-Z][A-Za-z\u2019 &/-]{1,40})\.\s+(.+)$")

def emit(cur, l):
    if cur["title"].lower().startswith("summary timeline"):
        cur["content"].append(("ol", re.sub(r"^(\d+[\.\)]\s+|[\u2022\-\*]\s+)", "", l)))
        return
    if l.endswith(":"):
        cur["content"].append(("lead", l)); cur["in_ul"] = True; return
    if cur["in_ul"]:
        cur["content"].append(("ul", re.sub(r"^([\u2022\-\*]\s+)", "", l))); return
    cur["in_ul"] = False
    cur["content"].append(("p", l))

def parse(text):
    lines = [l.strip() for l in text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "").split("\n")]
    items = [l for l in lines if l]
    title, preamble, articles, cur = None, [], [], None
    for l in items:
        m = ART_RE.match(l)
        if m:
            cur = {"num": m.group(1).upper(), "title": titlecase(m.group(2)), "content": [], "in_ul": False}
            articles.append(cur); continue
        if cur is None:
            if title is None:
                title = "Book Club Constitution" if l.upper().replace(" ", "") == "BOOKCLUBCONSTITUTION" else titlecase(l)
            else:
                preamble.append(l)
            continue
        if l == "End of Constitution":
            continue
        m = SEC_RE.match(l)
        if m:
            rest = m.group(2).strip()
            nm = NAME_RE.match(rest)
            if nm:
                cur["content"].append(("sec", (m.group(1), nm.group(1))))
                emit(cur, nm.group(2))
            else:
                cur["content"].append(("sec", (m.group(1), "")))
                if rest: emit(cur, rest)
            continue
        emit(cur, l)
    return title or "Book Club Constitution", " ".join(preamble), articles

def render_block(content):
    out, i = [], 0
    def group(kind):
        nonlocal i
        got = []
        while i < len(content) and content[i][0] == kind:
            got.append(content[i][1]); i += 1
        return got
    while i < len(content):
        kind, val = content[i]
        if kind == "sec":
            num, name = val
            head = '<span class="sec">Section ' + esc(num) + '.</span>'
            if name: head += " " + esc(name)
            out.append("<h3>" + head + "</h3>"); i += 1
        elif kind == "lead":
            out.append("<p>" + esc(val) + "</p>"); i += 1
        elif kind == "ul":
            out.append("<ul>" + "".join("<li>" + esc(v) + "</li>" for v in group("ul")) + "</ul>")
        elif kind == "ol":
            got = group("ol")
            out.append('<ol class="timeline">' + "".join("<li>" + esc(v) + "</li>" for v in got) + "</ol>")
        else:
            out.append("<p>" + esc(val) + "</p>"); i += 1
    return "\n".join(out)

def build_html(text):
    title, preamble, articles = parse(text)
    toc_lines = []
    for a in articles:
        num = a["num"]
        toc_lines.append('<li><a href="#article-' + num.lower() + '"><span class="n">' + num + '</span>' + esc(a["title"]) + '</a></li>')
    toc = "\n".join(toc_lines)
    art_parts = []
    for a in articles:
        num = a["num"]
        art_parts.append('<article id="article-' + num.lower() + '">\n<h2><span class="art-no">Article ' + num + '</span> ' + esc(a["title"]) + '</h2>\n' + render_block(a["content"]) + '\n</article>')
    arts = "\n\n".join(art_parts)
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>" + esc(title) + '</title>\n'
        '<meta name="description" content="The governing rules of the Book Club: meeting schedule, rescheduling, nominator selection, and ranked-choice book voting.">\n'
        '<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>\U0001F4D6</text></svg>">\n'
        "<style>\n" + CSS + "</style>\n</head>\n<body>\n"
        '<a class="skip" href="#content">Skip to contents</a>\n<div class="layout">\n'
        '<aside><nav class="toc" aria-label="Table of contents">\n<h2>Contents</h2>\n<ol>\n' + toc +
        '\n</ol>\n<button class="print-btn" onclick="window.print()">Print / save as PDF</button>\n</nav></aside>\n'
        '<main id="content">\n<header class="doc-head">\n<h1>' + esc(title) + '</h1>\n'
        '<p class="preamble">' + esc(preamble) + '</p>\n</header>\n\n' + arts + "\n\n"
        '<p class="end">End of Constitution</p>\n'
        '<p class="sync-note">Update this page by editing source.txt in the repository</p>\n'
        "</main>\n</div>\n</body>\n</html>\n")

def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--build":
        repo = sys.argv[2]
        text = open(os.path.join(repo, "source.txt"), encoding="utf-8", errors="replace").read()
        open(os.path.join(repo, "index.html"), "w", encoding="utf-8").write(build_html(text))
        print("built index.html from source.txt")
    elif len(sys.argv) >= 4 and sys.argv[1] == "--fetch":
        url, repo = sys.argv[2], sys.argv[3]
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        src = os.path.join(repo, "source.txt")
        if os.path.exists(src) and open(src, encoding="utf-8", errors="replace").read() == text:
            print("up to date"); return
        open(src, "w", encoding="utf-8").write(text)
        open(os.path.join(repo, "index.html"), "w", encoding="utf-8").write(build_html(text))
        print("updated from doc")
    else:
        print(__doc__); sys.exit(2)

if __name__ == "__main__":
    main()
