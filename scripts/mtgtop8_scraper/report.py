"""
报告生成模块
生成 Markdown 表格与 CSV，按稀有度/颜色/类别分类展示上位单卡。
中文卡名通过 Scryfall (lang:zhs) 查询，带本地缓存，避免自行翻译。
"""

import csv
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional

from .card_classifier import (
    RARITY_ORDER, RARITY_CN, COLOR_ORDER, COLOR_CN,
    TYPE_CATEGORIES, TYPE_CN,
)

SCRYFALL_API = "https://api.scryfall.com"
_last_scryfall_time = 0.0


def _rate_limit():
    global _last_scryfall_time
    elapsed = time.time() - _last_scryfall_time
    if elapsed < 0.12:
        time.sleep(0.12 - elapsed)
    _last_scryfall_time = time.time()


def _scryfall_search_zhs(english_name: str) -> Optional[str]:
    """通过 Scryfall search (lang:zhs) 获取中文印刷名"""
    _rate_limit()
    # !"name" 精确匹配，lang:zhs 限定简体中文印刷
    q = f'!"{english_name}" lang:zhs'
    url = f"{SCRYFALL_API}/cards/search?q={urllib.parse.quote(q)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MTG-Analysis/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(3)
        return None
    except Exception:
        return None

    if not data or not data.get("data"):
        return None
    for card in data["data"]:
        printed = card.get("printed_name")
        if printed and printed != card.get("name"):
            return printed
    return None


def get_chinese_names(names: list[str], cache: dict) -> dict:
    """
    批量获取中文卡名（逐张 Scryfall search，命中缓存的不重复查询）。
    遵守项目规则：中文卡名一律来自 API，不自行翻译；查不到则返回英文名。
    """
    result = {}
    uncached = []
    for n in names:
        if n in cache:
            result[n] = cache[n]
        else:
            uncached.append(n)

    if not uncached:
        print(f"    中文名全部命中缓存 ({len(names)} 张)")
        return result

    print(f"    查询中文卡名: {len(uncached)} 张 (Scryfall lang:zhs)...")
    for i, name in enumerate(uncached):
        if (i + 1) % 25 == 0:
            print(f"      进度: {i + 1}/{len(uncached)}")
        cn = _scryfall_search_zhs(name)
        result[name] = cn or name  # 查不到就用英文名
        cache[name] = result[name]
    return result


def load_chinese_cache(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_chinese_cache(filepath: str, cache: dict):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ============================================================
# Markdown 报告
# ============================================================

def _fmt_rarity(r: str) -> str:
    return f"{RARITY_CN.get(r, r)} ({r})"


def _fmt_color(c: str) -> str:
    return f"{COLOR_CN.get(c, c)} ({c})"


def _fmt_type(t: str) -> str:
    return f"{TYPE_CN.get(t, t)} ({t})"


def _card_table_rows(entries: list[dict], cn_names: dict) -> list[str]:
    """生成表格行（不含表头）"""
    rows = []
    for e in entries:
        cn = cn_names.get(e["name"], e["name"])
        sb = " (备牌)" if e.get("is_sideboard") else ""
        rows.append(
            f"| {e['name']} | {cn} | {_fmt_rarity(e['rarity'])} | "
            f"{_fmt_color(e['color_category'])} | {_fmt_type(e['type_category'])} | "
            f"{e['count']}{sb} |"
        )
    return rows


def _section_table(title: str, entries: list[dict], cn_names: dict) -> list[str]:
    """生成一个分类小节的表格"""
    lines = [f"### {title}（共 {len(entries)} 种 / {sum(e['count'] for e in entries)} 张）", ""]
    if not entries:
        lines += ["_无数据_", ""]
        return lines
    lines += [
        "| 卡牌(英) | 中文名 | 稀有度 | 颜色 | 类别 | 使用张数 |",
        "|---|---|---|---|---|---|",
    ]
    lines += _card_table_rows(entries, cn_names)
    lines.append("")
    return lines


def generate_markdown_report(all_data: dict, cn_names: dict,
                             months_back: int = 3) -> str:
    """
    生成完整的 Markdown 报告。

    all_data: {format_name: {"classified": {...}, "card_counts": {...}, "total_decks", "total_events"}}
    cn_names: {english_name: chinese_name}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# MTG Top8 上位单卡分析报告",
        "",
        f"- **数据来源**: https://www.mtgtop8.com/",
        f"- **时间范围**: 最近 {months_back} 个月",
        f"- **赛制**: Standard / Modern / Pauper",
        f"- **生成日期**: {today}",
        f"- **统计口径**: 比赛上位卡组（Top8/Top16）中出现的单卡，已排除基本地；备牌数量单独标注 `(备牌)`",
        "",
        "---",
        "",
    ]

    # 概览
    lines += ["## 概览", ""]
    lines += ["| 赛制 | 比赛数 | 卡组数 | 不同单卡数 | 总张数 |",
              "|---|---|---|---|---|"]
    for fmt, data in all_data.items():
        s = data["classified"]["summary"]
        lines.append(
            f"| {fmt.upper()} | {data['total_events']} | {data['total_decks']} | "
            f"{s['total_cards']} | {s['total_copies']} |"
        )
    lines += ["", "---", ""]

    # 各赛制详情
    for fmt, data in all_data.items():
        classified = data["classified"]
        lines += [f"## {fmt.upper()} 赛制", ""]

        # 按稀有度
        lines += [f"### 按稀有度分类", ""]
        for r in RARITY_ORDER:
            if r in classified["by_rarity"]:
                lines += _section_table(
                    f"{RARITY_CN.get(r, r)} ({r})",
                    classified["by_rarity"][r],
                    cn_names,
                )

        # 按颜色
        lines += [f"### 按颜色分类", ""]
        for c in COLOR_ORDER:
            if c in classified["by_color"]:
                lines += _section_table(
                    f"{COLOR_CN.get(c, c)} ({c})",
                    classified["by_color"][c],
                    cn_names,
                )

        # 按类别
        lines += [f"### 按类别分类", ""]
        type_order = list(TYPE_CATEGORIES.keys()) + ["Other"]
        for t in type_order:
            if t in classified["by_type"]:
                lines += _section_table(
                    f"{TYPE_CN.get(t, t)} ({t})",
                    classified["by_type"][t],
                    cn_names,
                )

        lines += ["---", ""]

    # 稀有度汇总
    lines += ["## 汇总统计", "", "### 各赛制稀有度分布（种数）", ""]
    lines += ["| 赛制 | " + " | ".join(_fmt_rarity(r) for r in RARITY_ORDER if any(r in d["classified"]["by_rarity"] for d in all_data.values())) + " |"]
    lines += ["|---|" + "---|" * sum(1 for r in RARITY_ORDER if any(r in d["classified"]["by_rarity"] for d in all_data.values()))]
    for fmt, data in all_data.items():
        cells = []
        for r in RARITY_ORDER:
            if any(r in d["classified"]["by_rarity"] for d in all_data.values()):
                cells.append(str(len(data["classified"]["by_rarity"].get(r, []))))
        lines.append(f"| {fmt.upper()} | " + " | ".join(cells) + " |")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# CSV 导出
# ============================================================

def export_csv(all_data: dict, cn_names: dict, filepath: str):
    """导出总 CSV: format, name, chinese_name, rarity, color, type, count, is_sideboard"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["format", "name", "chinese_name", "rarity",
                         "color", "type", "count", "is_sideboard"])
        for fmt, data in all_data.items():
            # 合并三个维度的条目，去重（同一张卡在三个维度都出现）
            seen = {}
            for bucket in (data["classified"]["by_rarity"],
                           data["classified"]["by_color"],
                           data["classified"]["by_type"]):
                for entries in bucket.values():
                    for e in entries:
                        key = (e["name"], e.get("is_sideboard", False))
                        if key not in seen:
                            seen[key] = e
            for e in seen.values():
                writer.writerow([
                    fmt,
                    e["name"],
                    cn_names.get(e["name"], e["name"]),
                    e["rarity"],
                    e["color_category"],
                    e["type_category"],
                    e["count"],
                    "Y" if e.get("is_sideboard") else "N",
                ])
    print(f"CSV 已导出: {filepath}")
