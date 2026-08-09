"""
一次性获取 Scryfall 所有中文卡牌（lang:zhs），提取中文卡名

用 /cards/search?q=lang:zhs&unique=card&lang=zhs 分页获取，
提取 name（英文）→ printed_name（中文）映射。
然后匹配 1,394 张新卡，补充中文卡名。
"""
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
NEW_CARDS_FILE = os.path.join(DATA_DIR, "spellbook_2005_new_cards.json")
ALL_CN_FILE = os.path.join(DATA_DIR, "all_chinese_cards.json")
CACHE_FILE = os.path.join(DATA_DIR, "chinese_names_spellbook.json")

SCRYFALL_API = "https://api.scryfall.com"
_last_request = 0.0


def rate_limit():
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < 0.15:
        time.sleep(0.15 - elapsed)
    _last_request = time.time()


def fetch_all_chinese_cards():
    """获取所有中文卡牌的 name → printed_name 映射"""
    print("获取所有中文卡牌（lang:zhs）...")
    cn_map = {}  # {english_name: chinese_name}

    # 第一页
    url = f"{SCRYFALL_API}/cards/search?q=lang%3Azhs+unique%3Acard&lang=zhs"
    page = 0

    while url:
        page += 1
        rate_limit()

        req = urllib.request.Request(url, headers={
            "User-Agent": "MTG-CardKeeper/1.0",
            "Accept": "application/json",
        })

        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 10 * (attempt + 1)
                    print(f"  429, 等待 {wait}s (attempt {attempt+1}/5)")
                    time.sleep(wait)
                elif e.code == 404:
                    data = None
                    break
                else:
                    print(f"  HTTP {e.code}: {e.reason}")
                    data = None
                    break
            except Exception as e:
                print(f"  错误: {e}")
                time.sleep(5)
                data = None
                break
        else:
            print(f"  第 {page} 页获取失败，跳过")
            break

        if not data:
            break

        cards = data.get("data", [])
        total = data.get("total_cards", 0)

        for card in cards:
            en_name = card.get("name", "")
            cn_name = card.get("printed_name", "")
            if en_name and cn_name and cn_name != en_name:
                cn_map[en_name] = cn_name

        if page % 10 == 1 or page == 1:
            print(f"  第 {page} 页: +{len(cards)} 张 (累计 {len(cn_map)}/{total})")

        # 处理双面牌：card_faces 中的每面也可能有 printed_name
        for card in cards:
            if "card_faces" in card:
                for face in card["card_faces"]:
                    en_face = face.get("name", "")
                    cn_face = face.get("printed_name", "")
                    if en_face and cn_face and cn_face != en_face:
                        if en_face not in cn_map:
                            cn_map[en_face] = cn_face

        url = data.get("next_page")

    print(f"\n共获取 {len(cn_map)} 个中文卡名映射")
    return cn_map


def main():
    # 1. 获取所有中文卡牌
    if os.path.exists(ALL_CN_FILE):
        print("加载已有中文卡牌缓存...")
        with open(ALL_CN_FILE, encoding="utf-8") as f:
            cn_map = json.load(f)
        print(f"  {len(cn_map)} 个映射")
    else:
        cn_map = fetch_all_chinese_cards()
        with open(ALL_CN_FILE, "w", encoding="utf-8") as f:
            json.dump(cn_map, f, ensure_ascii=False, indent=2)
        print(f"  保存到: {ALL_CN_FILE}")

    # 2. 匹配新卡
    with open(NEW_CARDS_FILE, encoding="utf-8") as f:
        new_cards = json.load(f)

    # 加载已有缓存
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)

    found = 0
    not_found = 0
    for name in new_cards:
        if name in cn_map:
            cache[name] = cn_map[name]
            found += 1
        elif name not in cache:
            cache[name] = ""
            not_found += 1

    print(f"\n匹配结果:")
    print(f"  有中文卡名: {found} 张")
    print(f"  无中文卡名: {not_found} 张")

    # 保存缓存
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"  缓存保存到: {CACHE_FILE}")

    # 样例
    print("\n  中文卡名样例:")
    for name in sorted(new_cards.keys()):
        cn = cache.get(name, "")
        if cn:
            print(f"    {name} -> {cn}")
            if found <= 20:
                continue
            break


if __name__ == "__main__":
    main()
