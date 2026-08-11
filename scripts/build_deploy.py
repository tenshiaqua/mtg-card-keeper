"""构建部署数据库：归档快照 + 合并数据源 + 计算趋势 + 写入根目录。

用法：
    python scripts/build_deploy.py

流程：
    1. 将当前 card_database.json 归档到 history/snapshot_YYYYMMDD.json
    2. 调用 card_keeper.database.build_database() 从所有数据源重建数据库
    3. 对比上一次快照，给每张卡牌添加 trend 字段（up/down/same/new）
    4. 将新数据库写入仓库根目录 card_database.json
"""

import json
import os
import sys
from datetime import datetime

# 将 scripts/ 加入路径，使 card_keeper 包可被导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from card_keeper.database import build_database  # noqa: E402

# 仓库根目录（scripts/ 的上一级）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY_DB = os.path.join(REPO_ROOT, "card_database.json")
HISTORY_DIR = os.path.join(REPO_ROOT, "history")


def archive_current():
    """归档当前部署数据库到 history/snapshot_YYYYMMDD.json。

    Returns:
        归档文件路径，若当前数据库不存在则返回 None。
    """
    if not os.path.exists(DEPLOY_DB):
        return None
    date = datetime.now().strftime("%Y%m%d")
    dest = os.path.join(HISTORY_DIR, f"snapshot_{date}.json")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    with open(DEPLOY_DB, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"📦 已归档当前快照: {dest}")
    return dest


def find_prev_snapshot(just_archived):
    """找到上一次的历史快照（排除刚归档的那个）。

    Returns:
        快照文件路径，若无则返回 None。
    """
    if not os.path.isdir(HISTORY_DIR):
        return None
    files = sorted(
        f for f in os.listdir(HISTORY_DIR)
        if f.startswith("snapshot_")
        and os.path.join(HISTORY_DIR, f) != just_archived
    )
    return os.path.join(HISTORY_DIR, files[-1]) if files else None


def compute_trends(cards, prev_path):
    """对比上一快照，给每张卡牌添加 trend 字段。

    trend = {"constructed": "up|down|same|new", "edh": "up|down|same|new"}
    """
    prev_cards = {}
    if prev_path and os.path.exists(prev_path):
        with open(prev_path, "r", encoding="utf-8") as f:
            prev_cards = json.load(f)
        print(f"📈 对比趋势基准: {prev_path}")

    for name, card in cards.items():
        trend = {"constructed": "new", "edh": "new"}
        if name in prev_cards:
            prev = prev_cards[name]
            # 构筑：总使用量（主牌+备牌）对比
            prev_total = sum(
                v.get("count", 0) + v.get("sideboard", 0)
                for v in prev.get("constructed", {}).values()
            )
            new_total = sum(
                v.get("count", 0) + v.get("sideboard", 0)
                for v in card.get("constructed", {}).values()
            )
            if new_total > prev_total:
                trend["constructed"] = "up"
            elif new_total < prev_total:
                trend["constructed"] = "down"
            else:
                trend["constructed"] = "same"
            # EDH：卡组数对比
            pe = (prev.get("edh") or {}).get("num_decks", 0)
            ne = (card.get("edh") or {}).get("num_decks", 0)
            if ne > pe:
                trend["edh"] = "up"
            elif ne < pe:
                trend["edh"] = "down"
            else:
                trend["edh"] = "same"
        card["trend"] = trend
    return cards


def main():
    print("=" * 60)
    print("构建部署数据库（含趋势计算）")
    print("=" * 60)

    # 1. 归档当前快照
    just_archived = archive_current()

    # 2. 从所有数据源构建新数据库（增量模式：保留旧数据库中已无用量的卡牌）
    db = build_database(existing_db_path=DEPLOY_DB)

    # 3. 计算趋势（对比上一次快照）
    prev = find_prev_snapshot(just_archived)
    compute_trends(db.cards, prev)

    # 4. 写入仓库根目录
    db.save(DEPLOY_DB)
    print(f"\n✅ 部署数据库已更新: {DEPLOY_DB}")
    print(f"   卡牌总数: {len(db.cards)} 种")

    # 5. 统计
    stats = db.stats()
    print(f"\n--- 统计 ---")
    print(f"  有构筑数据: {stats['has_constructed']}")
    print(f"  有 EDH 数据: {stats['has_edh']}")
    trend_counts = {"new": 0, "up": 0, "down": 0, "same": 0}
    for card in db.cards.values():
        t = card.get("trend", {}).get("constructed", "new")
        trend_counts[t] = trend_counts.get(t, 0) + 1
    print(f"  构筑趋势分布: {trend_counts}")


if __name__ == "__main__":
    main()
