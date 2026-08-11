"""
模拟 4 次双周抓取构建 usage_history.json。

由于 mtgtop8 旧数据无法可靠回溯，使用当前 card_database.json 的用量为基准，
为 4 个日期点（07.20 / 07.27 / 08.03 / 08.10）生成模拟趋势数据。

模拟策略：
  - 08.10 使用真实数据（当前 card_database.json）
  - 08.03 / 07.27 / 07.20 使用随机波动（±15%）模拟历史变化
  - 用量为 0 的卡保持 0

用法：
    python scripts/simulate_history.py
"""

import json
import os
import random
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEPLOY_DB = os.path.join(REPO_ROOT, "card_database.json")
HISTORY_FILE = os.path.join(REPO_ROOT, "usage_history.json")

FORMATS = ["standard", "modern", "pauper"]
SIM_DATES = ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10"]
REAL_DATE = "2026-08-10"  # 最后一个日期使用真实数据
VARIANCE = 0.15  # ±15% 随机波动

random.seed(42)  # 可复现


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("=" * 60)
    print("模拟 4 次双周抓取构建 usage_history.json")
    print("=" * 60)

    db = load_json(DEPLOY_DB)
    if not db:
        print("❌ 未找到 card_database.json")
        return

    history = {}
    real_count = 0

    for name, card in db.items():
        if name.startswith("__"):
            continue
        constructed = card.get("constructed", {})
        if not constructed:
            continue

        # 提取真实用量
        real_usage = {}
        has_data = False
        for fmt in FORMATS:
            fmt_data = constructed.get(fmt, {})
            if isinstance(fmt_data, dict):
                count = fmt_data.get("count", 0) or 0
                sideboard = fmt_data.get("sideboard", 0) or 0
                total = count + sideboard
            else:
                total = 0
            real_usage[fmt] = total
            if total > 0:
                has_data = True

        if not has_data:
            continue

        history[name] = {}

        # 为每个日期生成数据
        for date in SIM_DATES:
            if date == REAL_DATE:
                # 最后一个日期使用真实数据
                history[name][date] = dict(real_usage)
            else:
                # 模拟历史数据：随机波动
                simulated = {}
                for fmt in FORMATS:
                    real_val = real_usage[fmt]
                    if real_val == 0:
                        simulated[fmt] = 0
                    else:
                        # 随机波动 ±15%，但不会低于 0
                        factor = 1.0 + random.uniform(-VARIANCE, VARIANCE)
                        simulated[fmt] = max(0, int(real_val * factor))
                history[name][date] = simulated

        real_count += 1

    # 保存
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(HISTORY_FILE) / 1024
    print(f"\n✅ usage_history.json 已生成")
    print(f"   卡牌数: {real_count}")
    print(f"   数据点: {len(SIM_DATES)} 个 ({', '.join(SIM_DATES)})")
    print(f"   文件大小: {size_kb:.0f} KB")

    # 验证示例
    if history:
        k = list(history.keys())[0]
        print(f"\n   示例: {k}")
        for date in SIM_DATES:
            print(f"     {date}: {history[k][date]}")


if __name__ == "__main__":
    main()