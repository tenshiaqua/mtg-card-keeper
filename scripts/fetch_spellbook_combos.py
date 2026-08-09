"""
获取 Commander Spellbook 所有 combo 卡牌名称 + Scryfall 2005年前系列

输出：
  - scripts/data/spellbook_combo_cards.json: 所有 combo 卡名称列表
  - scripts/data/sets_2005.json: 2005年及之前的系列代码集合
"""
import json
import os
import time
import urllib.request
import urllib.error
import gzip

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SPELLBOOK_CARDS_FILE = os.path.join(DATA_DIR, "spellbook_combo_cards.json")
SETS_2005_FILE = os.path.join(DATA_DIR, "sets_2005.json")
BULK_CACHE = os.path.join(DATA_DIR, "default_cards.jsonl.gz")


def fetch_spellbook_cards():
    """获取 Commander Spellbook 所有 combo 卡牌名称"""
    print("=" * 60)
    print("获取 Commander Spellbook combo 卡牌列表")
    print("=" * 60)

    all_cards = []  # [{name, oracleId, identity, typeLine, ...}, ...]
    url = "https://backend.commanderspellbook.com/cards?limit=100&count=true"

    page = 0
    while url:
        page += 1
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "MTG-CardKeeper/1.0",
                    "Accept": "application/json",
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"  ⚠️ 429 速率限制，等待 {wait}s (attempt {attempt+1}/5)")
                    time.sleep(wait)
                else:
                    print(f"  ❌ HTTP {e.code}: {e.reason}")
                    return None
            except Exception as e:
                print(f"  ❌ 错误: {e}")
                time.sleep(5)
        else:
            print(f"  ❌ 第 {page} 页获取失败，跳过")
            break

        results = data.get("results", [])
        all_cards.extend(results)
        total = data.get("count", "?")

        if page % 10 == 0 or page == 1:
            print(f"  第 {page} 页: +{len(results)} 张 (累计 {len(all_cards)}/{total})")

        url = data.get("next")
        if url:
            time.sleep(1.5)  # 避免速率限制

    print(f"\n✅ 共获取 {len(all_cards)} 张 combo 卡")

    # 提取卡名集合
    card_names = {c["name"] for c in all_cards if c.get("name")}
    print(f"  去重后: {len(card_names)} 张唯一卡牌")

    # 保存完整数据（含额外字段）
    with open(SPELLBOOK_CARDS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_cards, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  已保存到: {SPELLBOOK_CARDS_FILE}")

    # 同时保存卡名集合（方便后续使用）
    names_file = os.path.join(DATA_DIR, "spellbook_combo_card_names.json")
    with open(names_file, "w", encoding="utf-8") as f:
        json.dump(sorted(card_names), f, ensure_ascii=False, indent=2)
    print(f"  卡名列表: {names_file}")

    return card_names


def extract_sets_2005_from_bulk():
    """从 Scryfall bulk data 中提取 2005 年及之前的系列"""
    print("\n" + "=" * 60)
    print("从 bulk data 提取 2005 年及之前的系列")
    print("=" * 60)

    # 先从 Scryfall /sets API 获取系列的 released_at 信息
    # 因为 bulk data 中的每张卡有 set 字段，但没有 set 的 released_at
    print("  从 Scryfall /sets API 获取系列发布日期...")

    sets_info = {}  # {set_code: {name, released_at, set_type}}
    url = "https://api.scryfall.com/sets"
    while url:
        req = urllib.request.Request(url, headers={
            "User-Agent": "MTG-CardKeeper/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for s in data.get("data", []):
            sets_info[s["code"]] = {
                "name": s.get("name", ""),
                "released_at": s.get("released_at", ""),
                "set_type": s.get("set_type", ""),
            }

        if data.get("has_more"):
            url = data.get("next_page")
            time.sleep(0.1)
        else:
            url = None

    print(f"  共获取 {len(sets_info)} 个系列信息")

    # 筛选 2005 年及之前的系列
    # 排除 promo/token/vanguard 等非标准系列类型
    EXCLUDE_TYPES = {"promo", "token", "vanguard", "memorabilia", "alchemy",
                     "ministry", "plane", "scheme", "arsenal", "spellbook",
                     "treasure_chest", "masterpiece"}

    sets_2005 = {}
    for code, info in sets_info.items():
        released = info.get("released_at", "")
        if not released:
            continue
        if released <= "2005-12-31":
            if info.get("set_type") not in EXCLUDE_TYPES:
                sets_2005[code] = info

    print(f"  2005年及之前的系列: {len(sets_2005)} 个")
    print(f"  示例: {dict(list(sets_2005.items())[:5])}")

    with open(SETS_2005_FILE, "w", encoding="utf-8") as f:
        json.dump(sets_2005, f, ensure_ascii=False, indent=2)
    print(f"  已保存到: {SETS_2005_FILE}")

    return sets_2005


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. 获取 Commander Spellbook combo 卡列表
    if os.path.exists(SPELLBOOK_CARDS_FILE):
        print("Combo 卡列表已存在，跳过获取")
        with open(SPELLBOOK_CARDS_FILE, encoding="utf-8") as f:
            all_cards = json.load(f)
        card_names = {c["name"] for c in all_cards if c.get("name")}
        print(f"  共 {len(card_names)} 张唯一 combo 卡")
    else:
        card_names = fetch_spellbook_cards()

    # 2. 获取 2005 年前的系列
    if os.path.exists(SETS_2005_FILE):
        print("\n2005年前系列列表已存在，跳过获取")
        with open(SETS_2005_FILE, encoding="utf-8") as f:
            sets_2005 = json.load(f)
        print(f"  共 {len(sets_2005)} 个系列")
    else:
        sets_2005 = extract_sets_2005_from_bulk()

    print("\n" + "=" * 60)
    print("准备就绪！")
    print(f"  Combo 卡: {len(card_names)} 张")
    print(f"  2005年前系列: {len(sets_2005)} 个")
    print("=" * 60)


if __name__ == "__main__":
    main()
