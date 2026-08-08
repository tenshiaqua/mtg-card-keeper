"""
MTG Top8 抓取与分析主入口

用法:
  python -m mtgtop8_scraper.main all            # 全流程：抓取+分类+生成报告
  python -m mtgtop8_scraper.main scrape         # 仅抓取原始数据
  python -m mtgtop8_scraper.main classify       # 仅分类（需先 scrape）
  python -m mtgtop8_scraper.main report         # 仅生成报告（需先 classify）
  python -m mtgtop8_scraper.main update         # 增量更新全流程（复用缓存）

可选参数:
  --months N        回溯月份数（默认 3）
  --formats X,Y     赛制（默认 standard,modern,pauper）
  --no-chinese      不查询中文卡名（加速）
  --no-sideboard    不统计备牌
  --max-pages N     每赛制最大翻页数（默认 8）
"""

import argparse
import json
import os
import sys
from datetime import datetime

from . import scraper
from . import card_classifier
from . import report

# 数据与缓存目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "..", "Report")

CARD_CACHE_PATH = os.path.join(DATA_DIR, "card_cache.json")
CN_CACHE_PATH = os.path.join(DATA_DIR, "chinese_cache.json")
PROGRESS_PATH = os.path.join(DATA_DIR, "progress.json")
RAW_PATH_TMPL = os.path.join(DATA_DIR, "raw_{date}.json")
PROCESSED_PATH_TMPL = os.path.join(DATA_DIR, "processed_{date}.json")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def cmd_scrape(args) -> dict:
    """抓取原始数据"""
    formats = [f.strip() for f in args.formats.split(",")]
    done_events, done_decks = set(), set()
    # 断点续传：加载本次运行已有的进度
    if os.path.exists(PROGRESS_PATH):
        ev, dk = scraper.load_progress(PROGRESS_PATH)
        done_events, done_decks = ev, dk
        print(f"加载断点续传进度: {len(done_events)} 比赛, {len(done_decks)} 卡组")

    print(f"\n开始抓取最近 {args.months} 个月的 {', '.join(f.upper() for f in formats)} 上位数据...")
    raw = scraper.scrape_all_cards(
        formats=formats,
        months_back=args.months,
        max_pages=args.max_pages,
        with_sideboard=not args.no_sideboard,
        done_events=done_events,
        done_decks=done_decks,
    )

    raw_path = RAW_PATH_TMPL.format(date=_today())
    scraper.save_raw_data(raw, raw_path)
    scraper.save_progress(PROGRESS_PATH, done_events, done_decks)
    return raw


def cmd_classify(args) -> dict:
    """分类：用 Scryfall 缓存补全卡牌信息，按稀有度/颜色/类别分类"""
    # 加载原始数据
    raw_path = getattr(args, "raw", None) or RAW_PATH_TMPL.format(date=_today())
    if not os.path.exists(raw_path):
        # 找最新的 raw_*.json
        files = sorted(f for f in os.listdir(DATA_DIR) if f.startswith("raw_"))
        if not files:
            print(f"未找到原始数据，请先运行 scrape。期望路径: {raw_path}")
            sys.exit(1)
        raw_path = os.path.join(DATA_DIR, files[-1])
        print(f"使用最新原始数据: {raw_path}")
    raw = scraper.load_raw_data(raw_path)

    # 加载卡牌信息缓存
    card_cache = card_classifier.load_card_cache(CARD_CACHE_PATH)

    all_data = {}
    for fmt, data in raw.items():
        classified, card_info = card_classifier.process_format_data(
            fmt, data["card_counts"], cache=card_cache
        )
        # 更新缓存
        card_cache.update(card_info)
        all_data[fmt] = {
            "classified": classified,
            "card_counts": data["card_counts"],
            "total_decks": data["total_decks"],
            "total_events": data["total_events"],
        }

    # 保存缓存与处理结果
    card_classifier.save_card_cache(CARD_CACHE_PATH, card_cache)
    processed_path = PROCESSED_PATH_TMPL.format(date=_today())
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"\n分类结果已保存: {processed_path}")
    print(f"卡牌信息缓存已更新: {CARD_CACHE_PATH} ({len(card_cache)} 张)")
    return all_data


def cmd_report(args) -> str:
    """生成 Markdown 表格与 CSV"""
    processed_path = getattr(args, "processed", None) or PROCESSED_PATH_TMPL.format(date=_today())
    if not os.path.exists(processed_path):
        files = sorted(f for f in os.listdir(DATA_DIR) if f.startswith("processed_"))
        if not files:
            print(f"未找到分类结果，请先运行 classify。期望路径: {processed_path}")
            sys.exit(1)
        processed_path = os.path.join(DATA_DIR, files[-1])
        print(f"使用最新分类结果: {processed_path}")
    with open(processed_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    # 收集所有卡牌英文名
    all_names = set()
    for fmt, data in all_data.items():
        for entries in data["classified"]["by_rarity"].values():
            for e in entries:
                all_names.add(e["name"])

    # 查询中文卡名（带缓存）
    if args.no_chinese:
        cn_names = {n: n for n in all_names}
        print("跳过中文卡名查询")
    else:
        cn_cache = report.load_chinese_cache(CN_CACHE_PATH)
        cn_names = report.get_chinese_names(sorted(all_names), cn_cache)
        report.save_chinese_cache(CN_CACHE_PATH, cn_cache)

    # 生成报告
    months_back = args.months
    md = report.generate_markdown_report(all_data, cn_names, months_back=months_back)
    os.makedirs(REPORT_DIR, exist_ok=True)
    date_tag = _today()
    md_path = os.path.join(REPORT_DIR, f"mtgtop8_cards_{date_tag}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\nMarkdown 报告已生成: {md_path}")

    csv_path = os.path.join(REPORT_DIR, f"mtgtop8_cards_{date_tag}.csv")
    report.export_csv(all_data, cn_names, csv_path)

    return md_path


def cmd_all(args):
    """全流程"""
    raw = cmd_scrape(args)
    all_data = cmd_classify(args)
    cmd_report(args)
    print("\n" + "=" * 60)
    print("全流程完成！")
    print("=" * 60)
    print(f"报告目录: {os.path.abspath(REPORT_DIR)}")
    print(f"下次运行可用 'update' 命令复用卡牌/中文缓存，仅抓取新比赛。")


def cmd_update(args):
    """增量更新：等价于 all，但复用缓存（card_cache / chinese_cache 跨次复用，
    progress.json 用于断点续传）。每赛制只抓最近 N 个月，保证窗口完整。"""
    # 清空旧的断点进度，重新抓取最近窗口（保证窗口完整），卡牌/中文缓存仍复用
    if os.path.exists(PROGRESS_PATH):
        os.remove(PROGRESS_PATH)
        print("清除断点进度，重新抓取最近窗口数据（卡牌/中文缓存仍复用）")
    cmd_all(args)


def main():
    parser = argparse.ArgumentParser(
        description="MTG Top8 上位单卡抓取与分类工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--months", type=int, default=3, help="回溯月份数（默认3）")
    common.add_argument("--formats", default="standard,modern,pauper", help="赛制（默认 standard,modern,pauper）")
    common.add_argument("--no-chinese", action="store_true", help="不查询中文卡名")
    common.add_argument("--no-sideboard", action="store_true", help="不统计备牌")
    common.add_argument("--max-pages", type=int, default=8, help="每赛制最大翻页数（默认8）")

    p_scrape = sub.add_parser("scrape", parents=[common], help="仅抓取原始数据")
    p_scrape.set_defaults(func=cmd_scrape)

    p_classify = sub.add_parser("classify", parents=[common], help="仅分类")
    p_classify.add_argument("--raw", help="指定原始数据文件路径")
    p_classify.set_defaults(func=cmd_classify)

    p_report = sub.add_parser("report", parents=[common], help="仅生成报告")
    p_report.add_argument("--processed", help="指定分类结果文件路径")
    p_report.set_defaults(func=cmd_report)

    p_all = sub.add_parser("all", parents=[common], help="全流程")
    p_all.set_defaults(func=cmd_all)

    p_update = sub.add_parser("update", parents=[common], help="增量更新全流程")
    p_update.set_defaults(func=cmd_update)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
