"""
过滤 combo_legacy 卡：只保留最新印刷版本在2005年及之前的卡

逻辑：
  对每张 combo_legacy 卡，检查其 sets 数组中所有系列的 released_at
  如果所有系列的 released_at <= "2005-12-31"，则保留 combo_legacy 标记
  如果有任何系列在2005年后发布，则移除 combo_legacy 标记
"""
import json
import os
import urllib.request
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
DEPLOY_DIR = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(DEPLOY_DIR, "card_database.json")
ALL_SETS_FILE = os.path.join(DATA_DIR, "all_sets_released.json")
SCRYFALL_API = "https://api.scryfall.com"


def fetch_all_sets_released():
    """从 Scryfall /sets API 获取所有系列的 {code: released_at} 映射"""
    print("从 Scryfall /sets API 获取所有系列发布日期...")
    sets_map = {}  # {code: released_at}
    url = f"{SCRYFALL_API}/sets"

    while url:
        req = urllib.request.Request(url, headers={
            "User-Agent": "MTG-CardKeeper/1.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        for s in data.get("data", []):
            sets_map[s["code"]] = s.get("released_at", "")

        if data.get("has_more"):
            url = data.get("next_page")
            time.sleep(0.1)
        else:
            url = None

    print(f"  共获取 {len(sets_map)} 个系列")
    return sets_map


def main():
    # 1. 获取所有系列发布日期
    if os.path.exists(ALL_SETS_FILE):
        print("加载已有系列发布日期缓存...")
        with open(ALL_SETS_FILE, encoding="utf-8") as f:
            all_sets = json.load(f)
        print(f"  {len(all_sets)} 个系列")
    else:
        all_sets = fetch_all_sets_released()
        with open(ALL_SETS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_sets, f, ensure_ascii=False, indent=2)
        print(f"  保存到: {ALL_SETS_FILE}")

    # 2. 加载数据库
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    # 3. 过滤 combo_legacy 卡
    print("\n过滤 combo_legacy 卡...")
    cutoff = "2005-12-31"
    keep = 0
    remove = 0
    removed_names = []
    unknown_sets = set()

    for name, card in db.items():
        if name.startswith("__"):
            continue
        if not card.get("combo_legacy"):
            continue

        card_sets = card.get("sets", [])
        has_post_2005 = False

        for set_code in card_sets:
            released = all_sets.get(set_code, "")
            if not released:
                unknown_sets.add(set_code)
                # 保守判断：未知系列视为2005年后
                has_post_2005 = True
                break
            if released > cutoff:
                has_post_2005 = True
                break

        if has_post_2005:
            card.pop("combo_legacy", None)
            remove += 1
            removed_names.append(name)
        else:
            keep += 1

    # 4. 统计
    total_legacy = sum(1 for k, v in db.items()
                       if not k.startswith("__") and v.get("combo_legacy"))
    print(f"  保留: {keep} 张（所有印刷都在2005年及之前）")
    print(f"  移除: {remove} 张（有2005年后的重印）")
    print(f"  剩余 combo_legacy: {total_legacy} 张")

    if unknown_sets:
        print(f"\n  ⚠️ 未知系列代码（{len(unknown_sets)} 个，被视为2005年后）:")
        for s in sorted(unknown_sets)[:20]:
            print(f"    {s}")

    # 5. 显示被移除的样例
    if removed_names:
        print(f"\n  被移除的卡样例（前20张）:")
        for name in sorted(removed_names)[:20]:
            card = db[name]
            sets_info = card.get("sets", [])
            # 找到2005年后的系列
            post_2005_sets = []
            for s in sets_info:
                released = all_sets.get(s, "????")
                if released > cutoff or not released:
                    post_2005_sets.append(f"{s}({released})")
            print(f"    {name}: 2005后重印系列 = {post_2005_sets[:5]}")

    # 6. 保存数据库
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(DB_PATH) / 1024
    print(f"\n数据库已保存: {size_kb:.0f} KB")
    print(f"总卡数: {len([k for k in db if not k.startswith('__')])} 张")


if __name__ == "__main__":
    main()
