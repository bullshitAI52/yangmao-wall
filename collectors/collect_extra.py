#!/usr/bin/env python3
"""Collect public feed items from 10 sources for the 羊毛情报墙 (PerkRadar extra) project.

Rules:
- RSS/Atom items kept only if published within the last 7 days (relative to run time).
- Max 200 items per source.
- Browser UA, 25s timeout per request, 1 retry on failure.
- Only public feeds; no login, no ordering.
Outputs: raw_extra.json (unified items), summary.json (per-source stats).
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TIMEOUT = 25
MAX_PER_SOURCE = 200
WINDOW_DAYS = 7

NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=WINDOW_DAYS)

SOURCES = [
    # id, name, group, type, urls (primary + fallbacks)
    ("steam", "Steam 特价", "游戏专区", "steam_json",
     ["https://store.steampowered.com/api/featuredcategories/?cc=cn&l=schinese"]),
    ("bundles", "Indie Bundles", "游戏专区", "feed",
     ["https://www.indiegamebundles.com/feed/"]),
    ("hostloc", "Hostloc", "论坛社区", "feed",
     ["https://hostloc.com/rss.php", "https://hostloc.com/forum.php?mod=rss"]),
    ("52pojie", "吾爱破解", "论坛社区", "feed",
     ["https://www.52pojie.cn/forum.php?mod=rss"]),
    ("sspai", "少数派", "软件精选", "feed",
     ["https://sspai.com/feed"]),
    ("oschina", "开源中国", "软件精选", "feed",
     ["https://www.oschina.net/news/rss"]),
    ("hellogithub", "HelloGitHub", "软件精选", "feed",
     ["https://github.com/521xueweihan/HelloGitHub/releases.atom",
      "https://hellogithub.com/rss"]),
    ("producthunt", "Product Hunt", "软件精选", "feed",
     ["https://www.producthunt.com/feed"]),
    ("smzdm", "什么值得买", "好价资讯", "feed",
     ["https://faxian.smzdm.com/feed", "https://www.smzdm.com/feed"]),
    ("ithome", "IT之家", "好价资讯", "feed",
     ["https://www.ithome.com/rss/"]),
]

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean_text(s, limit=160):
    if not s:
        return ""
    s = TAG_RE.sub(" ", s)
    s = unescape(s)
    s = WS_RE.sub(" ", s).strip()
    return s[:limit]


def fetch(url):
    """Fetch URL with 1 retry. Returns (bytes, error_str)."""
    last_err = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/atom+xml, application/json, text/xml, */*",
            })
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read(), None
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            if attempt == 0:
                time.sleep(2)
    return None, last_err


def parse_date(raw):
    """Parse RSS/Atom date string to aware datetime (UTC) or None."""
    if not raw:
        return None
    raw = raw.strip()
    # RFC 822 (RSS pubDate)
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        pass
    # ISO 8601 (Atom published/updated)
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(elem, names):
    for child in elem:
        if local(child.tag) in names:
            txt = "".join(child.itertext()) if child is not None else ""
            if txt and txt.strip():
                return txt.strip()
    return ""


def child_link(elem):
    # RSS: <link>text</link>; Atom: <link href="..." rel="alternate"/>
    for child in elem:
        if local(child.tag) == "link":
            href = child.get("href")
            if href:
                rel = child.get("rel", "alternate")
                if rel in ("alternate", ""):
                    return href.strip()
            elif child.text and child.text.strip():
                return child.text.strip()
    return ""


ENC_RE = re.compile(br'encoding=["\']([\w-]+)["\']', re.I)


def decode_feed(data):
    """Decode feed bytes honoring the XML declaration encoding (e.g. gbk)."""
    m = ENC_RE.search(data[:200])
    enc = m.group(1).decode("ascii", "ignore").lower() if m else "utf-8"
    if enc in ("gbk", "gb2312"):
        enc = "gb18030"
    try:
        text = data.decode(enc)
    except (UnicodeDecodeError, LookupError):
        text = data.decode("utf-8", errors="ignore")
    # Strip the XML declaration so ET doesn't complain about encodings.
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    start = text.find("<")
    return text[start:] if start > 0 else text


def parse_feed(data):
    """Parse RSS or Atom bytes -> list of (title, url, published_dt, summary_raw)."""
    root = ET.fromstring(decode_feed(data).encode("utf-8"))
    entries = []
    for elem in root.iter():
        if local(elem.tag) in ("item", "entry"):
            title = child_text(elem, ["title"])
            url = child_link(elem)
            date_raw = child_text(elem, ["pubDate", "published", "updated", "date"])
            summary_raw = child_text(elem, ["description", "summary", "content"])
            if title and url:
                entries.append((title, url, parse_date(date_raw), summary_raw))
    return entries


def collect_feed(source_id, name, group, urls):
    items = []
    last_err = None
    fetched = 0
    for url in urls:
        data, err = fetch(url)
        if data is None:
            last_err = f"{url} -> {err}"
            continue
        head = decode_feed(data)[:500].lower()
        if "<rss" not in head and "<feed" not in head:
            last_err = f"{url} -> response is not a feed (HTML page, likely a notice/block page)"
            continue
        try:
            entries = parse_feed(data)
        except Exception as e:  # noqa: BLE001
            last_err = f"{url} -> parse error: {type(e).__name__}: {e}"
            continue
        fetched = len(entries)
        for title, link, pub_dt, summary_raw in entries:
            if pub_dt is None or pub_dt < CUTOFF or pub_dt > NOW + timedelta(days=1):
                continue
            items.append({
                "title": clean_text(title, 300),
                "url": link,
                "source_id": source_id,
                "source_name": name,
                "group": group,
                "published_at": pub_dt.isoformat().replace("+00:00", "Z"),
                "summary": clean_text(summary_raw, 160),
            })
            if len(items) >= MAX_PER_SOURCE:
                break
        return items, fetched, None
    return items, fetched, last_err or "all endpoints failed"


def collect_steam(source_id, name, group, urls):
    items = []
    data, err = fetch(urls[0])
    if data is None:
        return items, 0, f"{urls[0]} -> {err}"
    try:
        payload = json.loads(data.decode("utf-8", errors="ignore"))
        specials = (payload.get("specials") or {}).get("items") or []
    except Exception as e:  # noqa: BLE001
        return items, 0, f"parse error: {type(e).__name__}: {e}"
    fetched = len(specials)
    now_iso = NOW.isoformat().replace("+00:00", "Z")
    for it in specials:
        app_id = it.get("id")
        title = it.get("name") or ""
        if not app_id or not title:
            continue
        disc = it.get("discount_percent") or 0
        orig = it.get("original_price")
        final = it.get("final_price")
        if orig is not None and final is not None:
            summary = f"-{disc}% ¥{orig / 100:.2f}→¥{final / 100:.2f}"
        else:
            summary = f"-{disc}%"
        items.append({
            "title": clean_text(title, 300),
            "url": f"https://store.steampowered.com/app/{app_id}",
            "source_id": source_id,
            "source_name": name,
            "group": group,
            "published_at": now_iso,  # Steam API has no publish date; fetch time used (noted in summary.json)
            "summary": summary,
        })
        if len(items) >= MAX_PER_SOURCE:
            break
    return items, fetched, None


def main():
    all_items = []
    summary = {
        "generated_at": NOW.isoformat().replace("+00:00", "Z"),
        "window_days": WINDOW_DAYS,
        "cutoff": CUTOFF.isoformat().replace("+00:00", "Z"),
        "notes": [
            "steam: 接口无发布日期，published_at 使用抓取时间（run time）",
            "RSS/Atom: 仅保留发布日期在最近 7 天内的条目",
        ],
        "sources": [],
    }
    for source_id, name, group, stype, urls in SOURCES:
        if stype == "steam_json":
            items, fetched, err = collect_steam(source_id, name, group, urls)
        else:
            items, fetched, err = collect_feed(source_id, name, group, urls)
        all_items.extend(items)
        summary["sources"].append({
            "source_id": source_id,
            "source_name": name,
            "group": group,
            "fetched": fetched,
            "kept": len(items),
            "error": err,
        })
        print(f"[{source_id}] fetched={fetched} kept={len(items)} error={err}", flush=True)

    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(out_dir, "raw_extra.json"), "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"TOTAL kept={len(all_items)}")


if __name__ == "__main__":
    main()
