"""
将 Commander Spellbook combo 卡（2005年前系列）补充到 card_database.json

不改动已有卡牌和逻辑，只添加新卡。
"""
import json
import os
import time
from collections import defaultdict

# ============================================================
# 路径
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DEPLOY_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(DEPLOY_DIR, "card_database.json")
NEW_CARDS_FILE = os.path.join(DATA_DIR, "spellbook_2005_new_cards.json")
CN_CACHE_FILE = os.path.join(DATA_DIR, "chinese_names_spellbook.json")
SETS_2005_FILE = os.path.join(DATA_DIR, "sets_2005.json")


def main():
    # ============================================================
    # 1. 加载数据
    # ============================================================
    print("=" * 60)
    print("加载数据...")
    print("=" * 60)

    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    existing_count = len([k for k in db.keys() if not k.startswith("__")])
    print(f"  当前数据库: {existing_count} 张卡")

    with open(NEW_CARDS_FILE, encoding="utf-8") as f:
        new_cards = json.load(f)
    print(f"  新卡数据: {len(new_cards)} 张")

    # 中文卡名缓存
    cn_cache = {}
    if os.path.exists(CN_CACHE_FILE):
        with open(CN_CACHE_FILE, encoding="utf-8") as f:
            cn_cache = json.load(f)
        print(f"  中文卡名缓存: {len(cn_cache)} 条")

    # 2005 年前系列（用于验证）
    with open(SETS_2005_FILE, encoding="utf-8") as f:
        sets_2005 = json.load(f)
    sets_2005_codes = set(sets_2005.keys())

    # ============================================================
    # 2. 更新新卡的中文卡名
    # ============================================================
    print("\n" + "=" * 60)
    print("更新新卡中文卡名...")
    print("=" * 60)

    has_cn = 0
    no_cn = 0
    for name, card in new_cards.items():
        cn = cn_cache.get(name, "")
        if cn:
            card["chinese_name"] = cn
            has_cn += 1
        else:
            no_cn += 1

    print(f"  有中文卡名: {has_cn} 张")
    print(f"  无中文卡名: {no_cn} 张（将使用英文名）")

    # ============================================================
    # 3. 补充到数据库（不改动已有卡）
    # ============================================================
    print("\n" + "=" * 60)
    print("补充新卡到数据库...")
    print("=" * 60)

    added = 0
    skipped = 0
    for name, card in new_cards.items():
        if name in db:
            skipped += 1
            continue
        db[name] = card
        added += 1

    print(f"  新增: {added} 张")
    print(f"  跳过（已存在）: {skipped} 张")

    final_count = len([k for k in db.keys() if not k.startswith("__")])
    print(f"  数据库总数: {existing_count} → {final_count}")

    # ============================================================
    # 4. 验证
    # ============================================================
    print("\n" + "=" * 60)
    print("验证...")
    print("=" * 60)

    # 验证新卡的 sets 字段包含 2005 年前系列
    verified = 0
    for name in new_cards:
        if name not in db:
            continue
        card_sets = db[name].get("sets", [])
        has_2005 = any(s in sets_2005_codes for s in card_sets)
        if has_2005:
            verified += 1

    print(f"  新卡中含 2005 年前系列: {verified}/{added}")

    # 验证已有卡未被修改
    sample_existing = ["Counterspell", "Lightning Bolt", "Sol Ring"]
    for name in sample_existing:
        if name in db:
            card = db[name]
            print(f"  已有卡 {name}: sets={len(card.get('sets', []))} 个, "
                  f"edh_tier={'有' if 'edh_tier' in card else '无'}, "
                  f"recommendation={'有' if 'recommendation' in card else '无'}")

    # ============================================================
    # 5. 保存
    # ============================================================
    print("\n" + "=" * 60)
    print("保存数据库...")
    print("=" * 60)

    # 无缩进压缩保存（与当前格式一致）
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(DB_PATH) / 1024
    print(f"  文件大小: {size_kb:.0f} KB")
    print(f"  保存到: {DB_PATH}")

    # ============================================================
    # 6. 统计摘要
    # ============================================================
    print("\n" + "=" * 60)
    print("统计摘要")
    print("=" * 60)

    rarity_count = defaultdict(int)
    color_count = defaultdict(int)
    type_count = defaultdict(int)
    for name in new_cards:
        if name not in db:
            continue
        c = db[name]
        rarity_count[c.get("rarity", "unknown")] += 1
        color_count[c.get("color_category", "unknown")] += 1
        type_count[c.get("type_category", "unknown")] += 1

    print(f"  新增 {added} 张 combo 卡（2005年前系列印刷）")
    print(f"  按稀有度: {dict(rarity_count)}")
    print(f"  按颜色: {dict(color_count)}")
    print(f"  按类型: {dict(type_count)}")

    # 涉及的 2005 年前系列
    sets_involved = set()
    for name in new_cards:
        if name not in db:
            continue
        for s in db[name].get("sets", []):
            if s in sets_2005_codes:
                sets_involved.add(s)
    print(f"  涉及系列: {len(sets_involved)} 个")

    print("\n✅ 完成！")
    print(f"  数据库: {existing_count} → {final_count} 张卡 (+{added})")
    print(f"  文件: {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
