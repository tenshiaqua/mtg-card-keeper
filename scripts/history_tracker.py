"""
用量历史追踪模块。

每次数据更新后，从 card_database.json 提取各赛制的构筑用量，
追加到 usage_history.json 中，用于前端趋势折线图。

用法：
    python scripts/history_tracker.py
"""

import json
import os
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEPLOY_DB = os.path.join(REPO_ROOT, "card_database.json")
HISTORY_FILE = os.path.join(REPO_ROOT, "usage_history.json")

FORMATS = ["standard", "modern", "pauper"]
MAX_HISTORY_POINTS = 52  # 保留最近 52 个周数据点（约 1 年）


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def week_monday(date):
    """返回 date 所在周的周一，作为趋势数据的唯一键。"""
    return date - timedelta(days=date.weekday())


def normalize_weekly_history(history):
    """将已有历史按周一归并，兼容此前可能写入的每日数据。

    同一周若有多个点，保留该周最后一个日期的值，避免改变用量含义。
    """
    normalized = {}
    for name, date_data in history.items():
        weekly = {}
        for date_key, usage in sorted(date_data.items()):
            try:
                date = datetime.strptime(date_key, "%Y-%m-%d").date()
            except ValueError:
                continue
            weekly[week_monday(date).isoformat()] = usage
        normalized[name] = weekly
    return normalized


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
    history = normalize_weekly_history(load_json(HISTORY_FILE))
    week_key = week_monday(datetime.now().date()).isoformat()

    # 检查本周是否已经记录过（避免重复）
    # 检查第一张卡是否已有本周一的记录
    for name, card in db.items():
        if name.startswith("__"):
            continue
        if name in history and week_key in history[name]:
            print(f"⚠ 本周 ({week_key}) 已有记录，跳过（避免重复追加）")
            # 即使本周已有数据，也保存归并后的历史，确保旧的每日点被压缩为周点。
            save_json(history, HISTORY_FILE)
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
        history[name][week_key] = usage_entry
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
