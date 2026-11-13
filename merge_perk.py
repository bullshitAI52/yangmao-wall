#!/usr/bin/env python3
"""合并 PerkRadar 快照（7 源）+ 补源 raw_extra.json（10 源）为羊毛情报墙统一 data.json。

统一字段：title, url, source_id, source_name, groups[], category, published_at, summary, heat
分组：游戏专区 / 云电脑 / 论坛社区 / 软件精选 / 好价资讯
「免费云电脑」为虚拟组：论坛社区源中标题/摘要命中云电脑关键词的条目同时归入该组。
热度 heat：新鲜度 + 羊毛信号估算（非来源站真实数据），页脚有注明。
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "latest.json"
EXTRA = Path.home() / "workspace/perk-extra/raw_extra.json"
OUT = BASE / "data.json"
REPORT = BASE / "report.md"

GROUP_OF_PERK = {
    "epic": "游戏专区",
    "linuxdo": "论坛社区",
    "v2ex": "论坛社区",
    "nodeseek": "论坛社区",
    "appinn": "软件精选",
    "ghxi": "软件精选",
    "iplaysoft": "软件精选",
}
CLOUD_RE = re.compile(r"云电脑|云主机|云服务器|虚拟主机|免费\s*VPS|VPS|云桌面|云游戏主机|云手机|免费主机|云端电脑|远程电脑", re.I)
FREE_RE = re.compile(r"免费|白嫖|0\s*元|零元|不要钱|free\b", re.I)
LIMITED_FREE_RE = re.compile(r"限免|限时免费|限时领取|限时特价|限时优惠")
DEAL_RE = re.compile(r"特价|优惠|降价|打折|促销|半价|史低|低价|折扣|薅|羊毛|补贴|红包|返现|-\d+\s*%")
MEMBER_RE = re.compile(r"会员|订阅|VIP|vip|Pro版|高级版|永久版")


def classify_extra(item):
    t = item.get("title", "")
    if item["source_id"] == "steam":
        return "低价优惠"
    if LIMITED_FREE_RE.search(t):
        return "限免"
    if FREE_RE.search(t):
        return "免费白嫖"
    if MEMBER_RE.search(t):
        return "会员订阅"
    if item.get("group") == "游戏专区":
        return "游戏"
    if DEAL_RE.search(t):
        return "低价优惠"
    return "其他"


def heat_of(published_iso, category, now):
    try:
        pub = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
    except Exception:
        pub = now
    age_h = max(0.0, (now - pub).total_seconds() / 3600)
    if age_h <= 6:
        base = 60
    elif age_h <= 24:
        base = 50
    elif age_h <= 72:
        base = 35
    else:
        base = 20
    bonus = {"免费白嫖": 25, "限免": 20, "低价优惠": 15, "游戏": 10, "会员订阅": 10}.get(category, 0)
    decay = min(15, int(age_h // 12))
    return max(5, min(100, base + bonus - decay))


def norm_url(u):
    return re.sub(r"[#?].*$", "", (u or "").strip().lower()).rstrip("/")


def main():
    now = datetime.now(timezone.utc)
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    extra = json.loads(EXTRA.read_text(encoding="utf-8"))
    items = []
    seen = set()

    for it in snap.get("items", []):
        key = norm_url(it["url"])
        if key in seen:
            continue
        seen.add(key)
        group = GROUP_OF_PERK.get(it["sourceId"], "其他")
        groups = [group]
        cat = it.get("category") or "其他"
        items.append({
            "title": it["title"],
            "url": it["url"],
            "source_id": it["sourceId"],
            "source_name": it["sourceName"],
            "groups": groups,
            "category": cat,
            "published_at": it.get("publishedAt"),
            "summary": "",
            "origin": "PerkRadar",
        })

    for it in extra:
        key = norm_url(it["url"])
        if key in seen:
            continue
        seen.add(key)
        cat = classify_extra(it)
        groups = [it["group"]]
        items.append({
            "title": it["title"],
            "url": it["url"],
            "source_id": it["source_id"],
            "source_name": it["source_name"],
            "groups": groups,
            "category": cat,
            "published_at": it.get("published_at"),
            "summary": it.get("summary") or "",
            "origin": "补源",
        })

    # 免费云电脑虚拟组：论坛社区条目命中关键词时追加分组
    cloud_hits = 0
    for it in items:
        if "论坛社区" in it["groups"] and CLOUD_RE.search(it["title"] + " " + it["summary"]):
            it["groups"] = ["云电脑"] + it["groups"]
            cloud_hits += 1

    for it in items:
        it["heat"] = heat_of(it["published_at"] or now.isoformat(), it["category"], now)

    items.sort(key=lambda x: (x["published_at"] or ""), reverse=True)

    from collections import Counter
    src_counter = Counter(it["source_name"] for it in items)
    cat_counter = Counter(it["category"] for it in items)
    grp_counter = Counter(g for it in items for g in it["groups"])
    wool = sum(v for k, v in cat_counter.items() if k != "其他")

    bj = now.astimezone(timezone(timedelta(hours=8)))
    data = {
        "generated_at": bj.strftime("%Y-%m-%d %H:%M"),
        "total": len(items),
        "wool": wool,
        "sources_ok": len(src_counter),
        "feeds_total": 17,
        "sources_total": 18,
        "source_status": [
            {"name": n, "count": c} for n, c in src_counter.most_common()
        ] + [
            {"name": "Hostloc", "count": 0, "note": "RSS 入口 404/拦截，本期 0 条"},
            {"name": "HelloGitHub", "count": 0, "note": "月刊节奏，近 7 天无新刊"},
        ],
        "items": items,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# 羊毛情报墙 · 数据报告",
        "",
        f"- 生成时间（北京）：{data['generated_at']}",
        f"- 总条数：{len(items)}（PerkRadar {sum(1 for i in items if i['origin']=='PerkRadar')} + 补源 {sum(1 for i in items if i['origin']=='补源')}）",
        f"- 其中羊毛（分类≠其他）：{wool}",
        f"- 有数据的来源：{len(src_counter)} / 18（Hostloc 本期失败 0 条、HelloGitHub 月刊近 7 天无新刊）",
        f"- 免费云电脑虚拟组命中：{cloud_hits} 条",
        "",
        "## 来源分布",
        *[f"- {n}: {c}" for n, c in src_counter.most_common()],
        "",
        "## 分类分布",
        *[f"- {n}: {c}" for n, c in cat_counter.most_common()],
        "",
        "## 分组分布（一件可多组）",
        *[f"- {n}: {c}" for n, c in grp_counter.most_common()],
        "",
        "口径：近 7 天在架；去重键为规范化 URL；PerkRadar 条目优先。热度为新鲜度+羊毛信号估算，非来源站真实数据。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"total={len(items)} wool={wool} sources={len(src_counter)} cloud={cloud_hits}")
    print("by source:", dict(src_counter))
    print("by category:", dict(cat_counter))
    print("by group:", dict(grp_counter))


if __name__ == "__main__":
    sys.exit(main())
