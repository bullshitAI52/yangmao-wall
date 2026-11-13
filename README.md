# 羊毛情报墙

把散布在论坛、软件站、游戏平台和好价站的免费 / 限免 / 低价情报聚合到一面墙上：近 7 天在架，按来源、分组、分类筛选，先到先得。

整合自开源项目 [PerkRadar](https://github.com/luobinger/PerkRadar)（MIT），并按「18 个来源分五组」的形态补齐了它没有的来源。配套的静态网页空间「羊毛情报墙」（Muse 空间，侧边栏）用同一份 `data/data.json` 渲染：头条（按热度前 5）、重点羊毛 / 全部情报 / 分组 / 分类标签、来源矩阵筛选、关键词搜索、收藏（本地）。

**只做信息聚合。** 条目来自公开订阅源，分类由标题规则推断，热度为新鲜度 + 羊毛信号估算，均非来源站真实数据；请以原文和活动官方说明为准。

## 数据（首期，2026-11-13）

- 近 7 天共 **354 条**，其中羊毛（分类≠其他）**69 条**；17 个订阅源中 15 个有数据
- PerkRadar 7 源经其自身抓取管线入库 121 条；补源 10 个公开 feed 直抓 233 条
- Hostloc 本期 0 条：RSS 入口 404、备用入口返回拦截提示页
- HelloGitHub 本期 0 条：月刊节奏，近 7 天无新刊（非抓取失败）
- 「免费云电脑」无独立站点：论坛社区源中标题/摘要命中云电脑/VPS/虚拟主机等关键词的条目同时归入该组（本期命中 1 条）
- 每个数字都能从 `data/data.json` 复算，口径与明细见 `report.md`

## 来源与分组

| 分组 | 来源 |
|---|---|
| 游戏专区 | Epic（PerkRadar）、Steam 特价、Indie Bundles |
| 云电脑 | 免费云电脑（论坛源关键词聚合） |
| 论坛社区 | LINUX DO 福利羊毛（PerkRadar）、V2EX 推广（PerkRadar）、NodeSeek（PerkRadar）、Hostloc、吾爱破解 |
| 软件精选 | 小众软件（PerkRadar）、异次元软件世界（PerkRadar）、果核剥壳（PerkRadar）、少数派、开源中国、HelloGitHub、Product Hunt |
| 好价资讯 | 什么值得买、IT之家 |

## 合并规则

- 统一字段：`title, url, source_id, source_name, groups[], category, published_at, summary, heat, origin`
- 分类：免费白嫖 / 限免 / 低价优惠 / 会员订阅 / 游戏 / 其他；PerkRadar 条目用其自带分类，补源按标题规则推断
- 去重键：规范化 URL（去查询串与锚点），PerkRadar 条目优先
- 在架窗口：近 7 天（Epic 按促销窗口，规则同 PerkRadar）

## 复现

```
# 1) PerkRadar 7 源：用它自己的管线抓一轮并导出快照
cd perkradar && npm ci
DATA_DIR=/path/to/perk-data npm run report
DATA_DIR=/path/to/perk-data DEALS_SNAPSHOT_DIR=/path/to/perk-wall \
  node --import tsx scripts/write-snapshot.ts   # 生成 latest.json

# 2) 补源 10 个公开 feed
python3 collectors/collect_extra.py            # 输出到 ~/workspace/perk-extra/raw_extra.json（脚本内路径可改）

# 3) 合并（latest.json 与 raw_extra.json 放在 merge_perk.py 预期位置）
python3 merge_perk.py                          # 生成 data/data.json 与 report.md
```

## 目录

```
perkradar/     上游 PerkRadar 源码（MIT，见其 LICENSE 与 THIRD_PARTY_NOTICES.md）
collectors/    补源采集脚本（Steam/Indie Bundles/Hostloc/吾爱破解/少数派/开源中国/HelloGitHub/Product Hunt/什么值得买/IT之家）
merge_perk.py  合并去重 + 分组/分类/热度 + 生成 report.md
data/          data.json（合并后的最终数据）
web/           情报墙空间导出的自包含 HTML 存档
report.md      数据报告（总数、各源/分类/分组分布，全部可复算）
```

## 许可与署名

- PerkRadar 代码为 MIT License（版权归其作者），`perkradar/` 内保留其 LICENSE；本仓库新增代码可自由使用。
- 各来源站点的内容版权归原站所有；本仓库仅聚合公开订阅源的标题、链接与短摘要。
