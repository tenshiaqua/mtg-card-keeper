"""
EDHREC By Type 数据抓取（纯 Python，无需浏览器 MCP）。

直接从 EDHREC 页面 HTML 中提取 __NEXT_DATA__ JSON，解析卡牌统计数据，
合并到 edhrec_cache.json。

EDHREC 的 By Type 页面 URL 结构:
  - Past 2 Years: /top/{type}        （默认，全量抓取）
  - Past Month:   /top/{type}/month  （月度增量更新）
  - Past Week:    /top/{type}/week   （可选）

每页返回 100 张卡（按使用率排序），覆盖该类型下最热门的卡牌。

用法:
  python -m card_keeper.fetch_edhrec_by_type fetch year     # 全量抓取 Past 2 Years
  python -m card_keeper.fetch_edhrec_by_type fetch month    # 月度更新 Past Month
  python -m card_keeper.fetch_edhrec_by_type fetch year --dry-run  # 试运行（不写入缓存）
  python -m card_keeper.fetch_edhrec_by_type list year      # 列出 URL
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
from datetime import datetime

# ============================================================
# 配置
# ============================================================

# 卡牌类型列表（与 EDHREC /top/{type} 路径一致）
CARD_TYPES = [
    "creatures",
    "instants",
    "sorceries",
    "artifacts",
    "enchantments",
    "planeswalkers",
    "lands",
]

# 时间范围 → URL 后缀
RANGE_SUFFIX = {
    "year": "",        # Past 2 Years（默认，无后缀）
    "month": "/month", # Past Month
    "week": "/week",   # Past Week
}

RANGE_LABEL = {
    "year": "Past 2 Years",
    "month": "Past Month",
    "week": "Past Week",
}

EDHREC_BASE = "https://edhrec.com"

# 文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(SCRIPT_DIR, "data", "edhrec_cache.json")
PROGRESS_PATH = os.path.join(SCRIPT_DIR, "data", "edhrec_fetch_progress.json")

# 请求间隔（秒），避免触发速率限制
REQUEST_DELAY = 0.5

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# URL 生成
# ============================================================

def build_urls(range_key: str = "year") -> list[dict]:
    """生成所有需要抓取的 URL。

    Returns:
        [{type, range, url, label}, ...]
    """
    suffix = RANGE_SUFFIX.get(range_key, "")
    urls = []
    for card_type in CARD_TYPES:
        url = f"{EDHREC_BASE}/top/{card_type}{suffix}"
        urls.append({
            "type": card_type,
            "range": range_key,
            "url": url,
            "label": f"Top {card_type} - {RANGE_LABEL.get(range_key, range_key)}",
        })
    return urls


# ============================================================
# 数据抓取
# ============================================================

def fetch_page(url: str, timeout: int = 20) -> str:
    """获取 EDHREC 页面 HTML"""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def extract_next_data(html: str) -> dict | None:
    """从 HTML 中提取 __NEXT_DATA__ JSON"""
    pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def parse_cards_from_next_data(next_data: dict) -> list[dict]:
    """从 __NEXT_DATA__ 中提取卡牌列表。

    支持两种页面结构:
    - top cards 列表页: json_dict.cardlists[].cardviews[]
    - 单卡页: json_dict.card
    """
    try:
        jd = next_data["props"]["pageProps"]["data"]["container"]["json_dict"]
    except (KeyError, TypeError):
        return []

    cards = []

    # 1. top cards 列表页
    for cardlist in jd.get("cardlists", []):
        for cv in cardlist.get("cardviews", []):
            num_decks = cv.get("num_decks", 0)
            potential_decks = cv.get("potential_decks", 0)
            inclusion = (num_decks / potential_decks) if potential_decks > 0 else 0.0
            cards.append({
                "name": cv.get("name", ""),
                "slug": cv.get("sanitized", cv.get("slug", "")),
                "num_decks": num_decks,
                "potential_decks": potential_decks,
                "inclusion": round(inclusion, 6),
                "salt": cv.get("salt", 0),
                "rarity": cv.get("rarity", ""),
                "primary_type": cv.get("primary_type", ""),
            })

    # 2. 单卡页（如果有）
    card = jd.get("card")
    if card and isinstance(card, dict):
        num_decks = card.get("num_decks", 0)
        potential_decks = card.get("potential_decks", 0)
        inclusion = (num_decks / potential_decks) if potential_decks > 0 else 0.0
        cards.append({
            "name": card.get("name", ""),
            "slug": card.get("slug", ""),
            "num_decks": num_decks,
            "potential_decks": potential_decks,
            "inclusion": round(inclusion, 6),
            "salt": card.get("salt", 0),
            "rarity": card.get("rarity", ""),
            "primary_type": card.get("primary_type", ""),
        })

    return cards


# ============================================================
# 缓存管理
# ============================================================

def load_cache() -> dict:
    """加载 EDHREC 缓存"""
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: dict):
    """保存 EDHREC 缓存"""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def merge_cards(cards: list[dict], cache: dict) -> tuple[dict, int]:
    """将卡牌列表合并到缓存（按 name 去重，保留最新）。

    Returns:
        (updated_cache, new_count)
    """
    new_count = 0
    for card in cards:
        name = card.get("name", "")
        if not name:
            continue
        if name not in cache:
            new_count += 1
        cache[name] = card
    return cache, new_count


# ============================================================
# 进度跟踪
# ============================================================

def load_progress() -> dict:
    if not os.path.exists(PROGRESS_PATH):
        return {"completed": [], "failed": [], "last_run": None}
    try:
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"completed": [], "failed": [], "last_run": None}


def save_progress(progress: dict):
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ============================================================
# 主抓取流程
# ============================================================

def fetch_all(range_key: str = "year", dry_run: bool = False) -> dict:
    """抓取所有类型的 top cards。

    Args:
        range_key: 时间范围 (year/month/week)
        dry_run: 试运行模式，不写入缓存

    Returns:
        {total_fetched, total_new, by_type, errors}
    """
    if range_key not in RANGE_SUFFIX:
        raise ValueError(f"未知时间范围: {range_key}，可选: {list(RANGE_SUFFIX.keys())}")

    urls = build_urls(range_key)
    cache = load_cache() if not dry_run else {}
    cache_before = len(cache)

    print(f"\n{'=' * 60}")
    print(f"  EDHREC By Type 抓取")
    print(f"  时间范围: {RANGE_LABEL[range_key]}")
    print(f"  类型数: {len(urls)}")
    print(f"  当前缓存: {cache_before} 张卡")
    print(f"  试运行: {'是' if dry_run else '否'}")
    print(f"{'=' * 60}\n")

    results = {
        "range": range_key,
        "total_fetched": 0,
        "total_new": 0,
        "by_type": {},
        "errors": [],
    }

    for i, item in enumerate(urls, 1):
        url = item["url"]
        card_type = item["type"]
        print(f"[{i}/{len(urls)}] {item['label']}")
        print(f"  URL: {url}")

        try:
            html = fetch_page(url)
            next_data = extract_next_data(html)

            if not next_data:
                msg = f"无法提取 __NEXT_DATA__"
                print(f"  ❌ {msg}")
                results["errors"].append({"url": url, "error": msg})
                continue

            cards = parse_cards_from_next_data(next_data)
            print(f"  提取: {len(cards)} 张卡")

            if not dry_run:
                cache, new_count = merge_cards(cards, cache)
            else:
                # 试运行也计算新增数
                new_count = sum(1 for c in cards if c.get("name", "") not in cache)

            results["total_fetched"] += len(cards)
            results["total_new"] += new_count
            results["by_type"][card_type] = {
                "fetched": len(cards),
                "new": new_count,
            }

            print(f"  新增: {new_count} 张")

        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code}: {e.reason}"
            print(f"  ❌ {msg}")
            results["errors"].append({"url": url, "error": msg})
        except Exception as e:
            msg = str(e)
            print(f"  ❌ {msg}")
            results["errors"].append({"url": url, "error": msg})

        # 速率限制
        if i < len(urls):
            time.sleep(REQUEST_DELAY)

    # 保存缓存
    if not dry_run:
        save_cache(cache)
        print(f"\n✅ 缓存已保存: {CACHE_PATH}")
        print(f"  {cache_before} → {len(cache)} 张卡（新增 {len(cache) - cache_before}）")

    # 保存进度
    progress = load_progress()
    progress["last_run"] = {
        "timestamp": datetime.now().isoformat(),
        "range": range_key,
        "total_fetched": results["total_fetched"],
        "total_new": results["total_new"],
        "errors": len(results["errors"]),
    }
    save_progress(progress)

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"  抓取完成")
    print(f"  总提取: {results['total_fetched']} 张")
    print(f"  总新增: {results['total_new']} 张")
    print(f"  错误: {len(results['errors'])} 个")
    if results["errors"]:
        print(f"  错误详情:")
        for e in results["errors"]:
            print(f"    - {e['url']}: {e['error']}")
    print(f"{'=' * 60}\n")

    return results


# ============================================================
# CLI
# ============================================================

def list_urls(range_key: str = "year"):
    """打印所有需要抓取的 URL"""
    urls = build_urls(range_key)
    print(f"\n{'=' * 60}")
    print(f"  EDHREC By Type 抓取 URL 列表")
    print(f"  时间范围: {RANGE_LABEL.get(range_key, range_key)}")
    print(f"  类型数: {len(urls)}")
    print(f"{'=' * 60}\n")
    for i, item in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] {item['label']}")
        print(f"     URL: {item['url']}")
    print()


def main():
    import sys

    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m card_keeper.fetch_edhrec_by_type fetch [range] [--dry-run]")
        print("  python -m card_keeper.fetch_edhrec_by_type list [range]")
        print()
        print("  range: year (Past 2 Years, 默认) | month (Past Month) | week (Past Week)")
        print()
        print("示例:")
        print("  python -m card_keeper.fetch_edhrec_by_type fetch year          # 全量抓取")
        print("  python -m card_keeper.fetch_edhrec_by_type fetch month          # 月度更新")
        print("  python -m card_keeper.fetch_edhrec_by_type fetch year --dry-run # 试运行")
        print("  python -m card_keeper.fetch_edhrec_by_type list year            # 列出 URL")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        range_key = sys.argv[2] if len(sys.argv) > 2 else "year"
        if range_key not in RANGE_SUFFIX:
            print(f"错误: 未知时间范围 '{range_key}'，可选: {list(RANGE_SUFFIX.keys())}")
            sys.exit(1)
        list_urls(range_key)

    elif cmd == "fetch":
        range_key = sys.argv[2] if len(sys.argv) > 2 else "year"
        dry_run = "--dry-run" in sys.argv
        if range_key not in RANGE_SUFFIX:
            print(f"错误: 未知时间范围 '{range_key}'，可选: {list(RANGE_SUFFIX.keys())}")
            sys.exit(1)
        fetch_all(range_key, dry_run=dry_run)

    else:
        print(f"未知命令: {cmd}")
        print("可用命令: fetch, list")
        sys.exit(1)


if __name__ == "__main__":
    main()
