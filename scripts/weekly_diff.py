"""
每周 mtgtop8 构筑数据变动对比报告。

对比最近两周的 snapshot，找出新增单卡（上周 0 → 本周 >0）和弃用单卡（上周 >0 → 本周 0）。
按系列（最新印刷）→ 颜色 → 类别三个维度组织表格。

用法：
    python scripts/weekly_diff.py              # 使用默认 snapshot 目录
    python scripts/weekly_diff.py --output report.md  # 指定输出文件
"""

import json
import os
import sys
from datetime import datetime

# 仓库根目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
HISTORY_DIR = os.path.join(REPO_ROOT, "history")
SETS_RELEASED_PATH = os.path.join(SCRIPT_DIR, "data", "all_sets_released.json")
SETS_INDEX_PATH = os.path.join(REPO_ROOT, "sets_index.json")

# 稀有度中文
RARITY_CN = {
    "mythic": "秘稀", "rare": "稀有", "uncommon": "非普通",
    "common": "普通", "special": "特殊", "bonus": "额外",
}

# 颜色中文
COLOR_CN = {
    "W": "白", "U": "蓝", "B": "黑", "R": "红", "G": "绿",
    "Colorless": "无色", "Multicolor": "多色",
}

# 类型中文
TYPE_CN = {
    "Creature": "生物", "Planeswalker": "鹏洛客", "Artifact": "神器",
    "Enchantment": "结界", "Instant": "瞬间", "Sorcery": "法术",
    "Land": "地", "Other": "其他",
}

# 格式化名
FORMAT_CN = {
    "standard": "标准", "modern": "摩登", "pauper": " pauper",
}


def load_json(path):
    """加载 JSON 文件"""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_total_usage(card):
    """计算卡牌所有赛制的总使用量（主牌+备牌）"""
    total = 0
    for fmt_data in card.get("constructed", {}).values():
        if isinstance(fmt_data, dict):
            total += fmt_data.get("count", 0) or 0
            total += fmt_data.get("sideboard", 0) or 0
    return total


def get_latest_set(card, sets_released):
    """获取卡牌最新印刷的系列代码"""
    sets = card.get("sets", [])
    if not sets:
        return "???"
    latest_code = None
    latest_date = ""
    for code in sets:
        date = sets_released.get(code, "")
        if date and (not latest_date or date > latest_date):
            latest_date = date
            latest_code = code
    return latest_code or sets[0]


def get_format_usage_detail(card):
    """获取各赛制用量详情字符串"""
    parts = []
    for fmt, data in sorted(card.get("constructed", {}).items()):
        if isinstance(data, dict):
            main = data.get("count", 0) or 0
            sb = data.get("sideboard", 0) or 0
            if main + sb > 0:
                label = FORMAT_CN.get(fmt, fmt)
                if sb > 0:
                    parts.append(f"{label} {main}+{sb}")
                else:
                    parts.append(f"{label} {main}")
    return ", ".join(parts) if parts else "—"


def compute_diff():
    """对比最近两周 snapshot，返回新增和弃用卡牌列表"""
    # 找到最近两个 snapshot
    if not os.path.isdir(HISTORY_DIR):
        print("❌ 未找到 history/ 目录")
        return None, None

    snapshots = sorted(
        [f for f in os.listdir(HISTORY_DIR) if f.startswith("snapshot_") and f.endswith(".json")]
    )
    if len(snapshots) < 2:
        print(f"❌ snapshot 数量不足 (需要至少 2 个，当前 {len(snapshots)} 个)")
        return None, None

    this_week_file = snapshots[-1]
    last_week_file = snapshots[-2]
    this_week_path = os.path.join(HISTORY_DIR, this_week_file)
    last_week_path = os.path.join(HISTORY_DIR, last_week_file)

    this_week = load_json(this_week_path)
    last_week = load_json(last_week_path)

    new_cards = []     # (name, this_week_card, this_usage)
    dropped_cards = []  # (name, last_week_card, last_usage)

    # 遍历本周所有卡牌
    for name, card in this_week.items():
        if name.startswith("__"):
            continue
        this_usage = get_total_usage(card)
        prev_card = last_week.get(name, {})
        prev_usage = get_total_usage(prev_card) if prev_card else 0

        if this_usage > 0 and prev_usage == 0:
            new_cards.append((name, card, this_usage))
        elif this_usage == 0 and prev_usage > 0:
            # 弃用卡用上周数据（含用量详情）
            dropped_cards.append((name, prev_card, prev_usage))

    # 也检查上周有但本周不在数据库中的卡（用上周数据）
    for name, card in last_week.items():
        if name.startswith("__"):
            continue
        if name not in this_week:
            prev_usage = get_total_usage(card)
            if prev_usage > 0:
                dropped_cards.append((name, card, prev_usage))

    return new_cards, dropped_cards, this_week_file, last_week_file


def organize_by_set_color_type(cards, sets_released):
    """按系列(最新) → 颜色 → 类别组织卡牌"""
    organized = {}  # {set_code: {color: {type: [card_info]}}}
    for name, card, usage in cards:
        set_code = get_latest_set(card, sets_released)
        color = card.get("color_category", "Unknown")
        type_cat = card.get("type_category", "Other")

        if set_code not in organized:
            organized[set_code] = {}
        if color not in organized[set_code]:
            organized[set_code][color] = {}
        if type_cat not in organized[set_code][color]:
            organized[set_code][color][type_cat] = []

        organized[set_code][color][type_cat].append({
            "name": name,
            "chinese_name": card.get("chinese_name", ""),
            "rarity": card.get("rarity", ""),
            "usage": usage,
            "card": card,
        })

    return organized


def generate_markdown(new_cards, dropped_cards, sets_released, sets_index,
                      this_week_file, last_week_file):
    """生成 Markdown 报告"""
    lines = []
    lines.append(f"# MTG 构筑赛制每周变动报告")
    lines.append(f"")
    lines.append(f"**对比区间**: `{last_week_file}` → `{this_week_file}`")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"")

    # 统计摘要
    lines.append(f"## 📊 统计摘要")
    lines.append(f"")
    lines.append(f"| 类别 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 🆕 新增单卡 | {len(new_cards)} 张 |")
    lines.append(f"| 🗑️ 弃用单卡 | {len(dropped_cards)} 张 |")
    lines.append(f"")

    # 新增单卡
    if new_cards:
        new_org = organize_by_set_color_type(new_cards, sets_released)
        lines.append(f"## 🆕 新增单卡（上周 0 → 本周 >0）")
        lines.append(f"")
        lines.append(f"共 **{len(new_cards)}** 张卡在本周首次出现在构筑上位牌表中。")
        lines.append(f"")
        generate_tables(lines, new_org, sets_released, sets_index, "new")

    # 弃用单卡
    if dropped_cards:
        dropped_org = organize_by_set_color_type(dropped_cards, sets_released)
        lines.append(f"## 🗑️ 弃用单卡（上周 >0 → 本周 0）")
        lines.append(f"")
        lines.append(f"共 **{len(dropped_cards)}** 张卡从本周构筑上位牌表中消失。")
        lines.append(f"")
        generate_tables(lines, dropped_org, sets_released, sets_index, "dropped")

    if not new_cards and not dropped_cards:
        lines.append(f"## ✅ 无变动")
        lines.append(f"")
        lines.append(f"本周构筑数据与上周相比没有新增或弃用的单卡。")
        lines.append(f"")

    return "\n".join(lines)


def generate_tables(lines, organized, sets_released, sets_index, label):
    """生成按系列 → 颜色 → 类别组织的表格"""
    # 按系列发布日期排序
    def sort_key_set(code):
        return sets_released.get(code, "9999-99-99")

    # 颜色排序
    COLOR_ORDER = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4, "Multicolor": 5, "Colorless": 6}

    # 类别排序
    TYPE_ORDER = {
        "Creature": 0, "Planeswalker": 1, "Artifact": 2,
        "Enchantment": 3, "Instant": 4, "Sorcery": 5, "Land": 6, "Other": 7,
    }

    for set_code in sorted(organized.keys(), key=sort_key_set):
        set_name = sets_index.get(set_code, set_code)
        set_date = sets_released.get(set_code, "????")
        set_label = f"{set_name} ({set_code.upper()})"
        if set_date:
            set_label += f" — {set_date}"

        lines.append(f"### {set_label}")
        lines.append(f"")

        for color in sorted(organized[set_code].keys(), key=lambda c: COLOR_ORDER.get(c, 99)):
            color_cn = COLOR_CN.get(color, color)
            lines.append(f"#### {color_cn}（{color}）")
            lines.append(f"")

            for type_cat in sorted(organized[set_code][color].keys(),
                                   key=lambda t: TYPE_ORDER.get(t, 99)):
                type_cn = TYPE_CN.get(type_cat, type_cat)
                lines.append(f"**{type_cn}**")
                lines.append(f"")
                lines.append(f"| 卡牌 | 中文名 | 稀有度 | 用量 |")
                lines.append(f"|------|--------|--------|------|")

                for item in sorted(organized[set_code][color][type_cat],
                                   key=lambda x: x["name"]):
                    name = item["name"]
                    cn = item["chinese_name"] or "—"
                    rarity = item["rarity"]
                    rarity_cn = RARITY_CN.get(rarity, rarity)
                    usage = item["usage"]
                    usage_detail = get_format_usage_detail(item["card"])

                    usage_str = f"{usage} 张 ({usage_detail})"

                    lines.append(f"| {name} | {cn} | {rarity_cn} | {usage_str} |")

                lines.append(f"")


def main():
    # 解析参数
    output_path = None
    args = sys.argv[1:]
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_path = args[idx + 1]

    if not output_path:
        output_path = os.path.join(REPO_ROOT, "weekly_diff_report.md")

    # 加载系列数据
    sets_released = load_json(SETS_RELEASED_PATH)
    sets_index = load_json(SETS_INDEX_PATH)

    # 计算差异
    result = compute_diff()
    if result is None:
        sys.exit(1)
    new_cards, dropped_cards, this_week, last_week = result

    # 生成报告
    report = generate_markdown(
        new_cards, dropped_cards, sets_released, sets_index,
        this_week, last_week
    )

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✅ 变动报告已生成: {output_path}")
    print(f"   新增: {len(new_cards)} 张 | 弃用: {len(dropped_cards)} 张")


if __name__ == "__main__":
    main()