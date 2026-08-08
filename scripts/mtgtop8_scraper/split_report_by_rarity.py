"""
按稀有度拆分报告。

- 秘稀 (mythic):  1 个文件，按 颜色 × 类别 组织
- 稀有 (rare):    1 个文件，按 颜色 × 类别 组织
- 非普通+普通:    拆成 8 个颜色文件（5单色 + 双色 + 三色及以上 + 无色），
                  文件内按类别区分，类别内按字母表排序

数据来源: mtgtop8_scraper/data/processed_*.json + card_cache.json + chinese_cache.json

用法:
  python -m mtgtop8_scraper.split_report_by_rarity [processed_json_path]
  不指定路径时自动取最新的 processed_*.json
"""

import os
import re
import sys
import json
from collections import defaultdict
from datetime import datetime

from .card_classifier import (
    RARITY_ORDER, RARITY_CN, COLOR_ORDER, COLOR_CN,
    TYPE_CATEGORIES, TYPE_CN,
)

# 类别展示顺序
TYPE_ORDER = list(TYPE_CATEGORIES.keys()) + ["Other"]


# ============================================================
# 颜色细分分类（用于 uncommon+common 拆分）
# ============================================================

# 8 个颜色组：(key, 中文名, 英文名, 文件后缀, 匹配函数)
def _color_group(colors: list) -> str:
    """根据 colors 列表返回细分颜色组 key"""
    if not colors:
        return "Colorless"
    if len(colors) == 1:
        return colors[0]  # W/U/B/R/G
    if len(colors) == 2:
        return "Dual"
    return "Multi3plus"  # 三色及以上


COLOR_GROUPS = [
    ("W", "白色", "White", "_W"),
    ("U", "蓝色", "Blue", "_U"),
    ("B", "黑色", "Black", "_B"),
    ("R", "红色", "Red", "_R"),
    ("G", "绿色", "Green", "_G"),
    ("Dual", "双色", "Dual Color", "_dual"),
    ("Multi3plus", "三色及以上", "3+ Color", "_3color"),
    ("Colorless", "无色", "Colorless", "_colorless"),
]


# ============================================================
# 通用工具
# ============================================================

def find_latest_processed(data_dir: str) -> str:
    files = [f for f in os.listdir(data_dir)
             if f.startswith("processed_") and f.endswith(".json")]
    if not files:
        return None
    files.sort()
    return os.path.join(data_dir, files[-1])


def merge_entries(all_data: dict, card_cache: dict) -> list[dict]:
    """
    合并三个赛制的卡牌条目（不区分赛制）。
    同一张卡的主牌/备牌分别按 (name, is_sideboard) 累加 count。
    从 card_cache 补充 colors 用于细分颜色组。
    """
    merged = {}
    for fmt, data in all_data.items():
        classified = data["classified"]
        for rarity, entries in classified["by_rarity"].items():
            for e in entries:
                key = (e["name"], e.get("is_sideboard", False))
                if key not in merged:
                    # 从缓存取 colors（用于双色/三色区分）
                    cache_info = card_cache.get(e["name"], {})
                    colors = cache_info.get("colors", [])
                    merged[key] = {
                        "name": e["name"],
                        "count": 0,
                        "is_sideboard": e.get("is_sideboard", False),
                        "rarity": e["rarity"],
                        "color_category": e["color_category"],
                        "colors": colors,
                        "color_group": _color_group(colors),
                        "type_category": e["type_category"],
                        "type_line": e.get("type_line", ""),
                    }
                merged[key]["count"] += e["count"]
    return list(merged.values())


def _fmt_color(c: str) -> str:
    return f"{COLOR_CN.get(c, c)} ({c})"


def _fmt_type(t: str) -> str:
    return f"{TYPE_CN.get(t, t)} ({t})"


def _fmt_rarity(r: str) -> str:
    return f"{RARITY_CN.get(r, r)} ({r})"


def _fmt_color_group(key: str) -> str:
    for k, cn, en, _ in COLOR_GROUPS:
        if k == key:
            return f"{cn} ({en})"
    return key


# ============================================================
# 概览
# ============================================================

def _build_header(title_scope: str, today: str, months_back: int,
                  overview_stats: list[dict]) -> list[str]:
    lines = [
        "# MTG Top8 上位单卡分析报告",
        "",
        f"- **数据来源**: https://www.mtgtop8.com/",
        f"- **时间范围**: 最近 {months_back} 个月",
        f"- **赛制**: Standard / Modern / Pauper（已合并，不区分赛制）",
        f"- **生成日期**: {today}",
        f"- **本文件范围**: {title_scope}",
        f"- **统计口径**: 比赛上位卡组中出现的单卡，已排除基本地；备牌数量单独标注 `(备牌)`",
        "",
        "---",
        "",
        "## 概览",
        "",
        "| 赛制 | 比赛数 | 卡组数 | 不同单卡数 | 总张数 |",
        "|---|---|---|---|---|",
    ]
    for s in overview_stats:
        lines.append(f"| {s['format'].upper()} | {s['total_events']} | {s['total_decks']} | "
                     f"{s['total_cards']} | {s['total_copies']} |")
    lines += ["", "---", ""]
    return lines


# ============================================================
# mythic / rare 文件：按颜色 × 类别（保持原逻辑）
# ============================================================

def build_rarity_group_report(entries: list[dict], group_title: str,
                              cn_names: dict) -> str:
    """生成 mythic / rare 单文件报告（按颜色×类别，数量降序）"""
    grouped = defaultdict(lambda: defaultdict(list))
    for e in entries:
        grouped[e["color_category"]][e["type_category"]].append(e)
    for color in grouped:
        for t in grouped[color]:
            grouped[color][t].sort(key=lambda x: x["count"], reverse=True)

    lines = [f"## {group_title} 卡牌 — 按颜色 × 类别分类", ""]
    total_cards = len({e["name"] for e in entries})
    total_copies = sum(e["count"] for e in entries)
    lines += [
        f"- **不同卡牌数**: {total_cards} 种",
        f"- **总张数**: {total_copies} 张",
        "",
    ]

    for color in COLOR_ORDER:
        if color not in grouped:
            continue
        color_entries = grouped[color]
        cc = len({e["name"] for t in color_entries.values() for e in t})
        cp = sum(e["count"] for t in color_entries.values() for e in t)
        lines += [f"### {_fmt_color(color)}（共 {cc} 种 / {cp} 张）", ""]
        for t in TYPE_ORDER:
            if t not in color_entries:
                continue
            t_entries = color_entries[t]
            tc = len({e["name"] for e in t_entries})
            tp = sum(e["count"] for e in t_entries)
            lines += [
                f"#### {_fmt_type(t)}（{tc} 种 / {tp} 张）", "",
                "| 卡牌(英) | 中文名 | 稀有度 | 类别 | 使用张数 |",
                "|---|---|---|---|---|",
            ]
            for e in t_entries:
                cn = cn_names.get(e["name"], e["name"])
                sb = " (备牌)" if e.get("is_sideboard") else ""
                lines.append(f"| {e['name']} | {cn} | {_fmt_rarity(e['rarity'])} | "
                             f"{_fmt_type(e['type_category'])} | {e['count']}{sb} |")
            lines.append("")
        lines.append("")
    lines.append("---")
    return "\n".join(lines)


# ============================================================
# uncommon+common 文件：按颜色细分（8个文件），类别内字母排序
# ============================================================

def build_color_split_report(entries: list[dict], color_key: str,
                             cn_names: dict) -> str:
    """
    生成单个颜色文件（uncommon+common 的一个颜色组）。
    文件内按类别分表格，类别内按英文名字母升序。
    """
    # 该颜色的条目已在外层筛选好
    grouped = defaultdict(list)
    for e in entries:
        grouped[e["type_category"]].append(e)

    # 类别内按英文名字母升序（不区分大小写）
    for t in grouped:
        grouped[t].sort(key=lambda x: x["name"].lower())

    total_cards = len({e["name"] for e in entries})
    total_copies = sum(e["count"] for e in entries)

    lines = [
        f"## {_fmt_color_group(color_key)} — 非普通+普通 卡牌",
        "",
        f"- **颜色组**: {_fmt_color_group(color_key)}",
        f"- **不同卡牌数**: {total_cards} 种",
        f"- **总张数**: {total_copies} 张",
        "",
        "---",
        "",
        f"### 按类别分类（类别内按字母表排序）",
        "",
    ]

    if not entries:
        lines += ["_无数据_", ""]
        return "\n".join(lines)

    for t in TYPE_ORDER:
        if t not in grouped:
            continue
        t_entries = grouped[t]
        tc = len({e["name"] for e in t_entries})
        tp = sum(e["count"] for e in t_entries)
        lines += [
            f"#### {_fmt_type(t)}（{tc} 种 / {tp} 张）", "",
            "| 卡牌(英) | 中文名 | 稀有度 | 颜色 | 使用张数 |",
            "|---|---|---|---|---|",
        ]
        for e in t_entries:
            cn = cn_names.get(e["name"], e["name"])
            sb = " (备牌)" if e.get("is_sideboard") else ""
            lines.append(
                f"| {e['name']} | {cn} | {_fmt_rarity(e['rarity'])} | "
                f"{_fmt_color_group(e['color_group'])} | {e['count']}{sb} |"
            )
        lines.append("")

    lines.append("---")
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    report_dir = os.path.join(script_dir, "..", "Report")

    if len(sys.argv) > 1:
        processed_path = sys.argv[1]
    else:
        processed_path = find_latest_processed(data_dir)
        if not processed_path:
            print("未找到 processed_*.json，请先运行 classify")
            sys.exit(1)

    processed_path = os.path.abspath(processed_path)
    print(f"数据来源: {processed_path}")

    with open(processed_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    # 加载卡牌信息缓存（用于 colors 字段区分双色/三色）
    card_cache_path = os.path.join(data_dir, "card_cache.json")
    card_cache = {}
    if os.path.exists(card_cache_path):
        with open(card_cache_path, "r", encoding="utf-8") as f:
            card_cache = json.load(f)
    print(f"卡牌信息缓存: {len(card_cache)} 张")

    # 加载中文卡名缓存
    cn_cache_path = os.path.join(data_dir, "chinese_cache.json")
    cn_names = {}
    if os.path.exists(cn_cache_path):
        with open(cn_cache_path, "r", encoding="utf-8") as f:
            cn_names = json.load(f)
    print(f"中文卡名缓存: {len(cn_names)} 张")

    # 合并赛制数据
    merged = merge_entries(all_data, card_cache)
    print(f"合并后总条目: {len(merged)} (含主牌/备牌分别计数)")

    # 概览统计
    overview_stats = []
    for fmt, data in all_data.items():
        s = data["classified"]["summary"]
        overview_stats.append({
            "format": fmt,
            "total_events": data["total_events"],
            "total_decks": data["total_decks"],
            "total_cards": s["total_cards"],
            "total_copies": s["total_copies"],
        })

    today = datetime.now().strftime("%Y-%m-%d")
    basename = os.path.basename(processed_path)
    m = re.search(r"processed_(\d+)\.", basename)
    date_tag = m.group(1) if m else datetime.now().strftime("%Y%m%d")

    os.makedirs(report_dir, exist_ok=True)

    # ---------- mythic 文件 ----------
    mythic_entries = [e for e in merged if e["rarity"] == "mythic"]
    if mythic_entries:
        header = _build_header("秘稀 (Mythic) 稀有度，按 颜色 × 类别 分类",
                               today, 3, overview_stats)
        body = build_rarity_group_report(mythic_entries, "秘稀 (Mythic)", cn_names)
        out_path = os.path.join(report_dir, f"mtgtop8_cards_{date_tag}_mythic.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n" + body)
        print(f"  生成: {os.path.basename(out_path)}  "
              f"({len({e['name'] for e in mythic_entries})} 种, "
              f"{os.path.getsize(out_path)/1024:.0f} KB)")

    # ---------- rare 文件 ----------
    rare_entries = [e for e in merged if e["rarity"] == "rare"]
    if rare_entries:
        header = _build_header("稀有 (Rare) 稀有度，按 颜色 × 类别 分类",
                               today, 3, overview_stats)
        body = build_rarity_group_report(rare_entries, "稀有 (Rare)", cn_names)
        out_path = os.path.join(report_dir, f"mtgtop8_cards_{date_tag}_rare.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n" + body)
        print(f"  生成: {os.path.basename(out_path)}  "
              f"({len({e['name'] for e in rare_entries})} 种, "
              f"{os.path.getsize(out_path)/1024:.0f} KB)")

    # ---------- uncommon+common 拆成 8 个颜色文件 ----------
    common_entries = [e for e in merged if e["rarity"] in ("uncommon", "common")]
    print(f"\n  非普通+普通: {len({e['name'] for e in common_entries})} 种，按颜色拆分:")

    for color_key, cn_name, en_name, suffix in COLOR_GROUPS:
        color_entries = [e for e in common_entries if e["color_group"] == color_key]
        card_count = len({e["name"] for e in color_entries})
        if not color_entries:
            print(f"    {_fmt_color_group(color_key)}: 无数据，跳过")
            continue

        header = _build_header(
            f"非普通+普通 | {_fmt_color_group(color_key)} | 按类别分类（类别内字母排序）",
            today, 3, overview_stats
        )
        body = build_color_split_report(color_entries, color_key, cn_names)
        out_path = os.path.join(report_dir, f"mtgtop8_cards_{date_tag}_common{suffix}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n" + body)
        print(f"    生成: {os.path.basename(out_path)}  "
              f"({card_count} 种, {os.path.getsize(out_path)/1024:.0f} KB)")

    print(f"\n拆分完成，文件已保存到 {os.path.abspath(report_dir)}")


if __name__ == "__main__":
    main()
