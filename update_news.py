#!/usr/bin/env python3
"""Baja RSS de varios medios y arma news.json para la página de inicio."""
import json, re, html, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

GN = "https://news.google.com/rss/headlines/section/topic/{}?hl=es-419&gl=AR&ceid=AR:es-419"
# (categoría, nombre por defecto, URL)  -> editá esta lista a gusto
FEEDS = [
    ("argentina", "Clarín", "https://www.clarin.com/rss/lo-ultimo/"),
    ("argentina", "La Nación", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml"),
    ("argentina", "Infobae", "https://www.infobae.com/arc/outboundfeeds/rss/"),
    ("argentina", "Google Noticias", GN.format("NATION")),
    ("deportes", "Olé", "https://www.ole.com.ar/rss/ultimas-noticias/"),
    ("deportes", "Google Noticias", GN.format("SPORTS")),
    ("mundo", "BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml"),
    ("mundo", "Google Noticias", GN.format("WORLD")),
    ("tecnologia", "Xataka", "https://www.xataka.com/feed"),
    ("tecnologia", "Google Noticias", GN.format("TECHNOLOGY")),
]
PER_FEED, MAX_TOTAL = 12, 120
NS = {"media": "http://search.yahoo.com/mrss/", "content": "http://purl.org/rss/1.0/modules/content/"}

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (news-homepage)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def parse_date(s):
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)

def find_image(it):
    for tag in ("media:content", "media:thumbnail"):
        for e in it.findall(tag, NS):
            u = e.get("url")
            if u and (e.get("medium") in (None, "image") or tag.endswith("thumbnail")):
                return u
    for e in it.findall("enclosure"):
        if (e.get("type") or "").startswith("image") and e.get("url"):
            return e.get("url")
    blob = (it.findtext("content:encoded", namespaces=NS) or "") + (it.findtext("description") or "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)', html.unescape(blob))
    return m.group(1) if m else ""

def parse(xml_bytes, cat, default_name):
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = it.find("source")
        source = (src.text.strip() if src is not None and src.text else default_name)
        if src is not None and title.endswith(" - " + source):   # Google Noticias agrega " - Medio"
            title = title[: -len(source) - 3]
        d = parse_date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"))
        out.append({"title": title, "link": link, "source": source, "cat": cat,
                    "image": find_image(it), "date": d.isoformat() if d else ""})
        if len(out) >= PER_FEED:
            break
    return out

def main():
    items, seen = [], set()
    for cat, name, url in FEEDS:
        try:
            for x in parse(fetch(url), cat, name):
                k = (x["cat"], x["link"])
                if k not in seen:
                    seen.add(k); items.append(x)
            print("OK  ", name, cat)
        except Exception as e:
            print("FALLÓ", name, cat, e)   # un medio caído no rompe el resto
    items.sort(key=lambda x: x["date"], reverse=True)
    data = {"updated": datetime.now(timezone.utc).isoformat(), "items": items[:MAX_TOTAL]}
    if not items:
        raise SystemExit("No se pudo bajar ninguna noticia; no piso news.json")
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(len(data["items"]), "noticias guardadas")

if __name__ == "__main__":
    main()
