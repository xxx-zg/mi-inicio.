#!/usr/bin/env python3
"""Baja RSS de varios medios y arma news.json para la página de inicio."""
import json, re, html, urllib.request
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

GN = "https://news.google.com/rss/headlines/section/topic/{}?hl=es-419&gl=AR&ceid=AR:es-419"
GS = "https://news.google.com/rss/search?q=site:{}&hl=es-419&gl=AR&ceid=AR:es-419"   # respaldo por sitio
# (categoría, nombre, URL del RSS, respaldo)  -> editá esta lista a gusto
FEEDS = [
    ("argentina", "Clarín", "https://www.clarin.com/rss/lo-ultimo/", GS.format("clarin.com")),
    ("argentina", "La Nación", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml", GS.format("lanacion.com.ar")),
    ("argentina", "C5N", "https://www.c5n.com/arc/outboundfeeds/rss/?outputType=xml", GS.format("c5n.com")),
    ("argentina", "Página 12", "https://www.pagina12.com.ar/rss/portada", GS.format("pagina12.com.ar")),
    ("argentina", "Perfil", "https://www.perfil.com/feed", GS.format("perfil.com")),
    ("argentina", "Ámbito", "https://www.ambito.com/rss/pages/home.xml", GS.format("ambito.com")),
    ("argentina", "TN", "https://tn.com.ar/arc/outboundfeeds/rss/?outputType=xml", GS.format("tn.com.ar")),
    ("argentina", "Telefe Noticias", "https://www.telefenoticias.com.ar/arc/outboundfeeds/rss/?outputType=xml", GS.format("telefenoticias.com.ar")),
    ("argentina", "El Destape", "https://www.eldestapeweb.com/feed", GS.format("eldestapeweb.com")),
    ("argentina", "El Cronista", "https://www.cronista.com/arc/outboundfeeds/rss/?outputType=xml", GS.format("cronista.com")),
    ("deportes", "TyC Sports", "https://www.tycsports.com/arc/outboundfeeds/rss/?outputType=xml", GS.format("tycsports.com")),
    ("deportes", "ESPN", "https://www.espn.com.ar/espn/rss/news", GS.format("espn.com.ar")),
    ("deportes", "Olé", "https://www.ole.com.ar/rss/ultimas-noticias/", GS.format("ole.com.ar")),
    ("mundo", "BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml", None),
    ("tecnologia", "Xataka", "https://www.xataka.com/feed", None),
]
# Medios que NO querés ver (se compara con el nombre y con el dominio del link)
BLOCKED = ["infobae"]
PER_FEED, MAX_TOTAL = 10, 150
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
        if any(b in source.lower() or b in link.lower() for b in BLOCKED):
            continue
        d = parse_date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"))
        out.append({"title": title, "link": link, "source": source, "cat": cat,
                    "image": find_image(it), "date": d.isoformat() if d else ""})
        if len(out) >= PER_FEED:
            break
    return out

def og_image(link):
    """Si la noticia no trae foto en el RSS, la busca en la propia página (og:image)."""
    try:
        txt = fetch(link)[:200000].decode("utf-8", "ignore")
        m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', txt)
             or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', txt))
        return html.unescape(m.group(1)) if m else ""
    except Exception:
        return ""

def main():
    items, seen = [], set()
    for cat, name, url, backup in FEEDS:
        got = []
        for u in (url, backup):
            if not u:
                continue
            try:
                got = parse(fetch(u), cat, name)
                if got:
                    print("OK  ", name, cat, "(respaldo)" if u == backup else "")
                    break
            except Exception as e:
                print("FALLÓ", name, cat, e)
        for x in got:
            k = (x["cat"], x["link"])
            if k not in seen:
                seen.add(k); items.append(x)
    # fotos que faltan (solo links directos, no los de Google Noticias)
    need = [x for x in items if not x["image"] and "news.google.com" not in x["link"]][:60]
    with ThreadPoolExecutor(8) as ex:
        for x, img in zip(need, ex.map(lambda z: og_image(z["link"]), need)):
            x["image"] = img
    items = [x for x in items if x["image"]]       # la página solo muestra noticias con foto
    items.sort(key=lambda x: x["date"], reverse=True)
    data = {"updated": datetime.now(timezone.utc).isoformat(), "items": items[:MAX_TOTAL]}
    if not items:
        raise SystemExit("No se pudo bajar ninguna noticia; no piso news.json")
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(len(data["items"]), "noticias guardadas")

if __name__ == "__main__":
    main()
