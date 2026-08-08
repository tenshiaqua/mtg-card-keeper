"""构建完整卡牌数据库。合并 mtgtop8 + EDHREC + Scryfall + 中文卡名。"""

import os
import sys

from .database import build_database, DATA_DIR


def main():
    print("=" * 60)
    print("构建卡牌数据库")
    print("=" * 60)

    db = build_database()

    out_path = os.path.join(DATA_DIR, "card_database.json")
    db.save(out_path)
    print(f"\n✅ 数据库已保存: {out_path}")
    print(f"   卡牌总数: {len(db.cards)} 种")

    # 打印统计
    stats = db.stats()
    print(f"\n--- 统计 ---")
    print(f"  有构筑数据: {stats['has_constructed']}")
    print(f"  有 EDH 数据: {stats['has_edh']}")
    print(f"  有中文名: {stats['has_chinese_name']}")
    print(f"\n  EDH 等级分布:")
    for tier, count in sorted(stats["edh_tier_distribution"].items()):
        print(f"    {tier}: {count}")
    print(f"\n  保留建议分布:")
    for rec, count in sorted(stats["recommendation_distribution"].items()):
        print(f"    {rec}: {count}")


if __name__ == "__main__":
    main()
