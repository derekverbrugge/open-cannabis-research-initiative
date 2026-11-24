#!/usr/bin/env python3
"""Generate public discovery assets from static HTML; standard library only."""
import csv, json, re, html
from pathlib import Path
from html.parser import HTMLParser
from xml.etree.ElementTree import Element, SubElement, tostring
ROOT=Path(__file__).resolve().parents[1]
BASE="https://opencannabisresearchinitiative.org/"
class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style"): self.skip+=1
        if tag in ("p","h1","h2","h3","li","tr","br","section"): self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in ("script","style"): self.skip=max(0,self.skip-1)
        if tag in ("p","td","th","li","tr","h1","h2","h3"): self.parts.append(" ")
    def handle_data(self,data):
        if not self.skip: self.parts.append(data)
def plain(s):
    p=Text(); p.feed(s)
    return "\n".join(" ".join(line.split()) for line in "".join(p.parts).splitlines() if line.strip())
def url(p): return BASE+("" if p.name=="index.html" else p.name)
pages=[]
for p in sorted(ROOT.glob("*.html")):
    if p.name in ("header.html","footer.html","404.html"): continue
    raw=p.read_text(encoding="utf-8")
    if not re.search(r"<head(?:\s|>)",raw,re.I): continue
    title=plain(re.search(r"<title>(.*?)</title>",raw,re.S|re.I).group(1)) if re.search(r"<title>(.*?)</title>",raw,re.S|re.I) else p.stem
    main=re.search(r"<main\b[^>]*>(.*?)</main>",raw,re.S|re.I)
    body=plain(main.group(1) if main else re.sub(r"^.*?</head>","",raw,flags=re.S|re.I))
    pages.append((p,title,body))
    schema={"@context":"https://schema.org","@type":"WebPage","name":title,"url":url(p),"publisher":{"@type":"Organization","name":"Open Cannabis Research Initiative","url":BASE}}
    if p.name.startswith("project-") or p.name=="case-report.html":
        schema["description"]="Proposed research, not an active clinical trial."
        schema["mainEntity"]={"@type":"CreativeWork","name":title,"creativeWorkStatus":"Proposed","genre":"Research proposal"}
    if p.name=="index.html": schema["mainEntity"]={"@type":"Organization","name":"Open Cannabis Research Initiative","url":BASE,"description":"Independent patient-led cannabis research advocacy initiative."}
    if p.name=="literature.html":
        schema["@type"]="CollectionPage"
        schema["mainEntity"]={"@type":"ItemList","itemListElement":[{"@type":"ListItem","position":i+1,"item":{"@type":"ScholarlyArticle","name":plain(t),"url":u}} for i,(u,t) in enumerate(re.findall(r'<th scope="row"><a href="([^"]+)">(.*?)</a>',raw,re.S))]}
    raw=re.sub(r'<link\b[^>]*rel=["\']canonical["\'][^>]*>','',raw,flags=re.I)
    raw=re.sub(r'<!-- OCRI GENERATED SEO START -->.*?<!-- OCRI GENERATED SEO END -->','',raw,flags=re.S)
    block='<!-- OCRI GENERATED SEO START --><link rel="canonical" href="'+url(p)+'"><script type="application/ld+json">'+json.dumps(schema,ensure_ascii=False).replace("</","<\\/")+'</script><!-- OCRI GENERATED SEO END -->'
    raw=raw.replace("</head>",block+"</head>",1)
    p.write_text(raw,encoding="utf-8")
sitemap=Element("urlset",xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
for p,title,body in pages: SubElement(SubElement(sitemap,"url"),"loc").text=url(p)
(ROOT/"sitemap.xml").write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n'+tostring(sitemap,encoding="utf-8")+b"\n")
intro="# Open Cannabis Research Initiative\n\n> Independent patient-led research advocacy. Proposed studies are not active trials; literature metadata is provisional and should be checked against original sources.\n"
(ROOT/"llms.txt").write_text(intro+"\n## Public pages\n\n"+"\n".join(f"- [{t}]({url(p)})" for p,t,b in pages)+"\n\n## Data\n\n- [Literature JSON]("+BASE+"literature.json)\n- [Literature CSV]("+BASE+"literature.csv)\n- [Full text]("+BASE+"llms-full.txt)\n",encoding="utf-8")
(ROOT/"llms-full.txt").write_text(intro+"\n"+"\n\n".join(f"## {t}\nSource: {url(p)}\n\n{b}" for p,t,b in pages)+"\n",encoding="utf-8")
raw=(ROOT/"literature.html").read_text(encoding="utf-8")
rows=[]
for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>",raw,re.S|re.I):
    cells=re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>",row,re.S|re.I)
    if len(cells)!=5 or not plain(cells[0]).isdigit(): continue
    link=re.search(r'href="([^"]+)"',cells[1])
    title=re.search(r"<a\b[^>]*>(.*?)</a>",cells[1],re.S)
    author=re.search(r"<small>(.*?)</small>",cells[1],re.S)
    rows.append(dict(year=int(plain(cells[0])),title=plain(title.group(1)) if title else plain(cells[1]),authors=plain(author.group(1)) if author else "",source_url=link.group(1) if link else "",evidence_type=plain(cells[2]),topics=plain(cells[3]),metadata_notes=plain(cells[4]),verification="Transcribed from site; independently unverified"))
assert rows, "No literature rows parsed"
(ROOT/"literature.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
with (ROOT/"literature.csv").open("w",encoding="utf-8",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(f"Generated {len(pages)} pages and {len(rows)} literature records")
