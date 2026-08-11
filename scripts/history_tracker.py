"""
用量历史追踪模块。

每次数据更新后，从 card_database.json 提取各赛制的构筑用量，
追加到 usage_history.json 中，用于前端趋势折线图。

用法：
    python scripts/history_tracker.py
"""

import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEPLOY_DB = os.path.join(REPO_ROOT, "card_database.json")
HISTORY_FILE = os.path.join(REPO_ROOT, "usage_history.json")

FORMATS = ["standard", "modern", "pauper"]
MAX_HISTORY_POINTS = 26  # 保留最近 26 次记录（约 1 年，双周更新）


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def main():
    print("=" * 60)
    print("更新用量历史记录")
    print("=" * 60)

    # 1. 加载当前数据库
    if not os.path.exists(DEPLOY_DB):
        print("❌ 未找到 card_database.json，跳过历史记录")
        return

    with open(DEPLOY_DB, "r", encoding="utf-8") as f:
        db = json.load(f)

    # 2. 加载现有历史
    history = load_json(HISTORY_FILE)
    today = datetime.now().strftime("%Y-%m-%d")

    # 检查是否今天已经记录过（避免重复）
    # 检查第一张卡是否已有今天的记录
    for name, card in db.items():
        if name.startswith("__"):
            continue
        if name in history and today in history[name]:
            print(f"⚠ 今天 ({today}) 已有记录，跳过（避免重复追加）")
            return
        break

    # 3. 提取用量数据
    updated = 0
    for name, card in db.items():
        if name.startswith("__"):
            continue
        constructed = card.get("constructed", {})
        if not constructed:
            continue

        # 提取各赛制用量（主牌+备牌）
        usage_entry = {}
        has_data = False
        for fmt in FORMATS:
            fmt_data = constructed.get(fmt, {})
            if isinstance(fmt_data, dict):
                count = fmt_data.get("count", 0) or 0
                sideboard = fmt_data.get("sideboard", 0) or 0
                total = count + sideboard
            else:
                total = 0
            usage_entry[fmt] = total
            if total > 0:
                has_data = True

        if not has_data:
            continue

        # 写入历史
        if name not in history:
            history[name] = {}
        history[name][today] = usage_entry
        updated += 1

    # 4. 裁剪旧记录（每张卡保留最近 MAX_HISTORY_POINTS 条）
    trimmed = 0
    for name in history:
        dates = sorted(history[name].keys())
        if len(dates) > MAX_HISTORY_POINTS:
            for old_date in dates[:-MAX_HISTORY_POINTS]:
                del history[name][old_date]
                trimmed += 1

    # 5. 保存
    save_json(history, HISTORY_FILE)
    size_kb = os.path.getsize(HISTORY_FILE) / 1024
    print(f"✅ 用量历史已更新: {HISTORY_FILE}")
    print(f"   记录卡牌数: {updated}")
    print(f"   文件大小: {size_kb:.0f} KB")
    if trimmed > 0:
        print(f"   裁剪旧记录: {trimmed} 条")


if __name__ == "__main__":
    main()