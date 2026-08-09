"""
为新加入的 combo 卡添加 combo_legacy 标记

这些卡的特点：
- 出现在 Commander Spellbook 的 combo 数据库中
- 在 2005 年及之前的系列中印刷过
- 很久没有重印（大部分只在老系列中出现）
- 有 combo 潜力
"""
import json
import os

DEPLOY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DEPLOY_DIR, "card_database.json")
NEW_CARDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spellbook_2005_new_cards.json")


def main():
    # 加载新卡名称列表
    with open(NEW_CARDS_FILE, encoding="utf-8") as f:
        new_cards = json.load(f)
    new_card_names = set(new_cards.keys())
    print(f"新卡数量: {len(new_card_names)}")

    # 加载数据库
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    # 添加标记
    tagged = 0
    already_tagged = 0
    for name in new_card_names:
        if name in db:
            if db[name].get("combo_legacy"):
                already_tagged += 1
            else:
                db[name]["combo_legacy"] = True
                tagged += 1

    # 统计
    total_legacy = sum(1 for k, v in db.items()
                       if not k.startswith("__") and v.get("combo_legacy"))

    print(f"新标记: {tagged} 张")
    print(f"已有标记: {already_tagged} 张")
    print(f"总计 combo_legacy 卡: {total_legacy} 张")

    # 保存（无缩进压缩格式）
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(DB_PATH) / 1024
    print(f"\n数据库已保存: {size_kb:.0f} KB")

    # 验证
    sample_names = ["Academy Rector", "Academy Researchers", "Counterspell", "Lightning Bolt"]
    for name in sample_names:
        if name in db:
            card = db[name]
            print(f"  {name}: combo_legacy={card.get('combo_legacy', False)}")


if __name__ == "__main__":
    main()
