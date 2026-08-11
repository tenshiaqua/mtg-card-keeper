"""
首次回填脚本：模拟 4 次双周更新覆盖最近 2 个月。

每次抓取一个 2 周窗口（非重叠），从 4 次抓取中提取卡牌用量，
汇总写入 usage_history.json，供前端趋势图使用。

用法（首次运行一次即可）：
    cd e:\Codes\MTG\card_keeper\deploy
    python scripts/backfill_history.py

注意：
  - 需要网络连接访问 mtgtop8.com
  - 4 次抓取约需 10-20 分钟（取决于网络和 mtgtop8 响应速度）
  - 回填完成后，后续双周 workflow 自动追加新数据点
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SCRIPTS_DIR = SCRIPT_DIR  # scripts/ 目录
HISTORY_FILE = os.path.join(REPO_ROOT, "usage_history.json")
# scraper 保存 raw 数据到 scripts/mtgtop8_scraper/data/
SCRAPER_DATA_DIR = os.path.join(SCRIPTS_DIR, "mtgtop8_scraper", "data")
PROGRESS_PATH = os.path.join(SCRAPER_DATA_DIR, "progress.json")

FORMATS = ["standard", "modern", "pauper"]
NUM_WINDOWS = 4  # 回填 4 个窗口（8 周 = 2 个月）
WINDOW_WEEKS = 2  # 每个窗口 2 周


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def run_scraper(start_date: str, end_date: str, window_idx: int) -> dict:
    """运行 scraper 抓取指定日期范围内的数据。

    Returns:
        {format_name: {"card_counts": {name: count}, ...}}
    """
    print(f"\n{'=' * 60}")
    print(f"窗口 {window_idx + 1}/{NUM_WINDOWS}: {start_date} ~ {end_date}")
    print(f"{'=' * 60}")

    # 使用 subprocess 运行 scraper
    cmd = [
        sys.executable, "-m", "scripts.mtgtop8_scraper.main", "scrape",
        "--start-date", start_date,
        "--end-date", end_date,
        "--formats", "standard,modern,pauper",
        "--max-pages", "8",
        "--no-chinese",  # 回填时跳过中文查询，加速
    ]

    # 从 deploy/ 根目录运行（scraper 模块路径为 scripts.mtgtop8_scraper.main）
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=False, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"⚠ scraper 超时（5分钟），跳过窗口 {window_idx + 1}")
        return {}

    if result.returncode != 0:
        print(f"⚠ scraper 返回非零退出码: {result.returncode}")
        return {}

    # 加载最新的 raw 数据，并重命名为窗口专属文件（避免被后续窗口覆盖）
    raw_files = sorted(
        f for f in os.listdir(SCRAPER_DATA_DIR)
        if f.startswith("raw_") and f.endswith(".json") and "_w" not in f
    )
    if not raw_files:
        print("⚠ 未找到 raw_*.json")
        return {}

    raw_path = os.path.join(SCRAPER_DATA_DIR, raw_files[-1])
    # 重命名为窗口专属文件
    window_raw_path = os.path.join(SCRAPER_DATA_DIR, f"raw_backfill_w{window_idx + 1}.json")
    os.rename(raw_path, window_raw_path)
    print(f"  已保存窗口数据: {window_raw_path}")
    return load_json(window_raw_path)


def extract_usage(raw_data: dict, window_end_date: str) -> dict:
    """从 raw 数据中提取每张卡的各赛制用量。

    Returns:
        {card_name: {date: {standard: N, modern: N, pauper: N}}}
    """
    history = {}
    for fmt_name, fmt_data in raw_data.items():
        if fmt_name.startswith("__"):
            continue
        card_counts = fmt_data.get("card_counts", {})
        for key, count in card_counts.items():
            # 分离主牌和备牌
            is_sb = key.endswith(" [SB]")
            card_name = key.replace(" [SB]", "") if is_sb else key

            if card_name not in history:
                history[card_name] = {}

            if window_end_date not in history[card_name]:
                history[card_name][window_end_date] = {
                    "standard": 0, "modern": 0, "pauper": 0,
                }

            if fmt_name in history[card_name][window_end_date]:
                history[card_name][window_end_date][fmt_name] += count

    return history


def main():
    print("=" * 60)
    print("首次回填用量历史（模拟 4 次双周更新）")
    print("=" * 60)
    print(f"覆盖范围: 最近 {NUM_WINDOWS * WINDOW_WEEKS} 周 ({NUM_WINDOWS} 个窗口)")
    print()

    # 计算 4 个非重叠 2 周窗口
    # 窗口 0: [now-8w, now-6w] (最旧)
    # 窗口 1: [now-6w, now-4w]
    # 窗口 2: [now-4w, now-2w]
    # 窗口 3: [now-2w, now]   (最新)
    now = datetime.now()
    all_history = {}

    for i in range(NUM_WINDOWS):
        # 从最旧到最新
        weeks_ago_end = (NUM_WINDOWS - 1 - i) * WINDOW_WEEKS
        weeks_ago_start = weeks_ago_end + WINDOW_WEEKS

        end_date = now - timedelta(weeks=weeks_ago_end)
        start_date = now - timedelta(weeks=weeks_ago_start)

        window_end_label = end_date.strftime("%Y-%m-%d")
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # 抓取数据
        raw_data = run_scraper(start_str, end_str, i)

        if not raw_data:
            print(f"⚠ 窗口 {i + 1} 抓取失败，跳过")
            continue

        # 清理进度文件，避免下一窗口被断点续传影响
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)

        # 提取用量
        window_history = extract_usage(raw_data, window_end_label)

        # 合并到总历史
        for card_name, date_data in window_history.items():
            if card_name not in all_history:
                all_history[card_name] = {}
            all_history[card_name].update(date_data)

        print(f"  窗口 {i + 1} 完成: {len(window_history)} 张卡")

    # 保存
    if all_history:
        save_json(all_history, HISTORY_FILE)
        size_kb = os.path.getsize(HISTORY_FILE) / 1024
        print(f"\n{'=' * 60}")
        print(f"✅ 回填完成！")
        print(f"   总卡牌数: {len(all_history)}")
        print(f"   文件: {HISTORY_FILE} ({size_kb:.0f} KB)")

        # 统计每张卡的数据点数
        point_counts = [len(v) for v in all_history.values()]
        if point_counts:
            print(f"   平均数据点/卡: {sum(point_counts) / len(point_counts):.1f}")
            print(f"   最多数据点: {max(point_counts)}")
            print(f"   最少数据点: {min(point_counts)}")
    else:
        print("\n❌ 回填失败：未获取到任何数据")
        sys.exit(1)


if __name__ == "__main__":
    main()