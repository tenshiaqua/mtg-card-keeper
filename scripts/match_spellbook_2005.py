"""
从 Scryfall bulk data 中交叉匹配 combo 卡 + 2005年前系列，
提取符合条件的新卡信息并补充到 card_database.json。

逻辑：
  1. 加载 combo 卡名集合（7916张）+ 2005年前系列代码集合（70个）
  2. 遍历 bulk data，找出在 2005 年前系列中印刷过的 combo 卡
  3. 同时收集这些卡的 Scryfall 信息、所有印刷系列、中文卡名
  4. 筛选出不在当前数据库中的新卡
  5. 补充到 card_database.json（不改动已有卡）
"""
import json
import os
import gzip
import time
from collections import defaultdict

# ============================================================
# 路径
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DEPLOY_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(DEPLOY_DIR, "card_database.json")
BULK_CACHE = os.path.join(DATA_DIR, "default_cards.jsonl.gz")
SPELLBOOK_NAMES_FILE = os.path.join(DATA_DIR, "spellbook_combo_card_names.json")
SETS_2005_FILE = os.path.join(DATA_DIR, "sets_2005.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "spellbook_2005_new_cards.json")

# 类型分类映射（与 card_classifier.py 一致）
TYPE_CATEGORIES = {
    "Creature": ["Creature"],
    "Planeswalker": ["Planeswalker"],
    "Battle": ["Battle"],
    "Artifact": ["Artifact"],
    "Enchantment": ["Enchantment"],
    "Instant": ["Instant"],
    "Sorcery": ["Sorcery"],
    "Kindred": ["Kindred", "Tribal"],
    "Land": ["Land"],
}


def classify_color(colors):
    if not colors:
        return "Colorless"
    if len(colors) == 1:
        return colors[0]
    return "Multicolor"


def classify_type(type_line):
    if not type_line:
        return "Other"
    type_lower = type_line.lower()
    for category, keywords in TYPE_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in type_lower:
                return category
    return "Other"


def build_card_info(card):
    """从 Scryfall 卡牌数据构建标准化信息（与 card_classifier.py 一致）"""
    if "card_faces" in card and "type_line" not in card:
        front = card["card_faces"][0]
        type_line = front.get("type_line", "")
        mana_cost = front.get("mana_cost", "")
        colors = front.get("colors", card.get("colors", []))
    else:
        type_line = card.get("type_line", "")
        mana_cost = card.get("mana_cost", "")
        colors = card.get("colors", [])

    return {
        "name": card.get("name", ""),
        "rarity": card.get("rarity", "unknown"),
        "colors": colors,
        "color_category": classify_color(colors),
        "type_line": type_line,
        "type_category": classify_type(type_line),
        "cmc": card.get("cmc", 0),
        "mana_cost": mana_cost,
    }


def main():
    # ============================================================
    # 1. 加载数据
    # ============================================================
    print("=" * 60)
    print("加载数据...")
    print("=" * 60)

    # combo 卡名集合
    with open(SPELLBOOK_NAMES_FILE, encoding="utf-8") as f:
        combo_names = set(json.load(f))
    print(f"  Combo 卡: {len(combo_names)} 张")

    # 2005 年前系列代码集合
    with open(SETS_2005_FILE, encoding="utf-8") as f:
        sets_2005 = json.load(f)
    sets_2005_codes = set(sets_2005.keys())
    print(f"  2005年前系列: {len(sets_2005_codes)} 个")

    # 当前数据库卡名集合
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)
    existing_names = {k for k in db.keys() if not k.startswith("__")}
    print(f"  当前数据库: {len(existing_names)} 张卡")

    # ============================================================
    # 2. 遍历 bulk data，找出符合条件的卡
    # ============================================================
    print("\n" + "=" * 60)
    print("遍历 bulk data，交叉匹配 combo 卡 + 2005年前系列")
    print("=" * 60)

    # 符合条件的卡：combo 卡且至少在一个 2005 年前系列中印刷过
    # qualified_cards: {card_name: {info, sets, chinese_name}}
    qualified_cards = {}
    # 临时存储：每张卡的所有印刷信息
    card_printings = defaultdict(lambda: {"sets": set(), "chinese_names": {}, "latest_info": None, "latest_released": ""})

    total_lines = 0
    matched_combo = 0
    matched_2005 = 0

    with gzip.open(BULK_CACHE, "rt", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            if total_lines % 50000 == 0:
                print(f"  进度: {total_lines} 行, combo匹配 {len(qualified_cards)} 张")

            try:
                card = json.loads(line)
            except json.JSONDecodeError:
                continue

            name = card.get("name", "")
            if not name or name not in combo_names:
                continue

            matched_combo += 1
            set_code = card.get("set", "")
            released_at = card.get("released_at", "")

            # 记录系列
            card_data = card_printings[name]
            card_data["sets"].add(set_code)

            # 记录中文卡名（lang=zhs 且有 printed_name）
            if card.get("lang") == "zhs" and card.get("printed_name"):
                card_data["chinese_names"][set_code] = card["printed_name"]

            # 记录最新印刷版本的信息（用 released_at 最新的）
            if not card_data["latest_info"] or released_at > card_data["latest_released"]:
                card_data["latest_info"] = build_card_info(card)
                card_data["latest_released"] = released_at

            # 检查是否在 2005 年前系列中印刷过
            if set_code in sets_2005_codes:
                matched_2005 += 1
                if name not in qualified_cards:
                    qualified_cards[name] = True

    print(f"\n  bulk data 总行数: {total_lines}")
    print(f"  combo 卡匹配次数: {matched_combo}")
    print(f"  在 2005 年前系列印刷过的 combo 卡: {len(qualified_cards)} 张")

    # ============================================================
    # 3. 筛选新卡（不在当前数据库中的）
    # ============================================================
    print("\n" + "=" * 60)
    print("筛选新卡（不在当前数据库中的）")
    print("=" * 60)

    new_card_names = {n for n in qualified_cards if n not in existing_names}
    existing_in_db = {n for n in qualified_cards if n in existing_names}

    print(f"  符合条件的 combo 卡总数: {len(qualified_cards)}")
    print(f"  已在数据库中: {len(existing_in_db)}")
    print(f"  新卡（需补充）: {len(new_card_names)}")

    if not new_card_names:
        print("\n✅ 没有新卡需要补充，所有符合条件的卡都已在数据库中")
        return

    # ============================================================
    # 4. 构建新卡数据
    # ============================================================
    print("\n" + "=" * 60)
    print(f"构建 {len(new_card_names)} 张新卡数据")
    print("=" * 60)

    new_cards = {}
    for name in sorted(new_card_names):
        data = card_printings[name]
        info = data["latest_info"]

        if not info:
            print(f"  ⚠️ {name}: 无 Scryfall 信息，跳过")
            continue

        # 中文卡名：优先取第一个可用的
        chinese_name = ""
        if data["chinese_names"]:
            # 取任意一个中文印刷版本
            chinese_name = list(data["chinese_names"].values())[0]

        # 构建卡牌条目（与现有数据库格式一致）
        card_entry = {
            "name": name,
            "chinese_name": chinese_name,
            "rarity": info["rarity"],
            "colors": info["colors"],
            "color_category": info["color_category"],
            "type_line": info["type_line"],
            "type_category": info["type_category"],
            "cmc": info["cmc"],
            "mana_cost": info["mana_cost"],
            "constructed": {},   # 无构筑数据
            "edh": None,         # 无 EDH 数据
            "trend": {},         # 无趋势数据
            "sets": sorted(data["sets"]),  # 所有印刷系列代码
        }
        new_cards[name] = card_entry

    print(f"  成功构建: {len(new_cards)} 张")
    print(f"  有中文卡名: {sum(1 for c in new_cards.values() if c['chinese_name'])} 张")
    print(f"  无中文卡名: {sum(1 for c in new_cards.values() if not c['chinese_name'])} 张")

    # 保存新卡数据到临时文件（供检查）
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(new_cards, f, ensure_ascii=False, indent=2)
    print(f"\n  新卡数据已保存到: {OUTPUT_FILE}")

    # 打印样例
    print("\n  样例（前 10 张）:")
    for name in sorted(new_cards.keys())[:10]:
        c = new_cards[name]
        sets_2005_in_card = [s for s in c["sets"] if s in sets_2005_codes]
        print(f"    {name} ({c['chinese_name'] or '???'}) "
              f"[{c['rarity']}, {c['color_category']}, {c['type_category']}] "
              f"2005前系列: {sets_2005_in_card[:3]}")

    # ============================================================
    # 5. 统计摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("统计摘要")
    print("=" * 60)

    # 按稀有度统计
    rarity_count = defaultdict(int)
    color_count = defaultdict(int)
    type_count = defaultdict(int)
    for c in new_cards.values():
        rarity_count[c["rarity"]] += 1
        color_count[c["color_category"]] += 1
        type_count[c["type_category"]] += 1

    print(f"  按稀有度: {dict(rarity_count)}")
    print(f"  按颜色: {dict(color_count)}")
    print(f"  按类型: {dict(type_count)}")

    # 涉及的 2005 年前系列
    sets_involved = set()
    for c in new_cards.values():
        for s in c["sets"]:
            if s in sets_2005_codes:
                sets_involved.add(s)
    print(f"  涉及的 2005 年前系列: {len(sets_involved)} 个")
    for s in sorted(sets_involved):
        print(f"    {s}: {sets_2005.get(s, {}).get('name', '?')} ({sets_2005.get(s, {}).get('released_at', '?')})")


if __name__ == "__main__":
    main()
