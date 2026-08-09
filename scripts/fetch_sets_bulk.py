"""从 Scryfall Bulk Data (JSONL.gz) 批量提取卡牌系列信息。

比逐卡 API 查询快 50 倍：下载一个压缩文件 → 流式解析 → 一次性提取所有卡的系列。

用法：
    python scripts/fetch_sets_bulk.py

流程：
    1. 下载 Scryfall default_cards bulk data（JSONL.gz 格式）
    2. 流式解析每一行（内存友好，不一次性加载全文件）
    3. 提取每张卡的所有印刷系列（set code + set name）
    4. 更新 card_database.json：每张卡添加 sets 字段
    5. 生成 sets_index.json：{set_code: set_name}
"""

import gzip
import json
import os
import sys
import time
import urllib.request

# 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEPLOY_DB = os.path.join(REPO_ROOT, "card_database.json")
SETS_INDEX_PATH = os.path.join(REPO_ROOT, "sets_index.json")
BULK_CACHE = os.path.join(SCRIPT_DIR, "data", "default_cards.jsonl.gz")

SCRYFALL_BULK_API = "https://api.scryfall.com/bulk-data"


def get_bulk_download_uri() -> str:
    """获取 default_cards bulk data 的下载地址"""
    req = urllib.request.Request(
        SCRYFALL_BULK_API,
        headers={"User-Agent": "MTG-CardKeeper/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    for entry in data["data"]:
        if entry["type"] == "default_cards":
            uri = entry.get("jsonl_download_uri") or entry.get("download_uri")
            compressed = entry.get("compressed_size", 0)
            print(f"  bulk data 更新时间: {entry['updated_at'][:10]}")
            if compressed:
                print(f"  压缩后大小: {compressed / 1024 / 1024:.1f} MB")
            return uri

    raise RuntimeError("未找到 default_cards bulk data")


def download_bulk(uri: str):
    """下载 bulk data 到本地缓存"""
    if os.path.exists(BULK_CACHE):
        size_mb = os.path.getsize(BULK_CACHE) / 1024 / 1024
        print(f"  已有缓存: {BULK_CACHE} ({size_mb:.1f} MB)")
        print(f"  如需重新下载，请删除该文件。")
        return

    print(f"  下载中: {uri}")
    os.makedirs(os.path.dirname(BULK_CACHE), exist_ok=True)
    req = urllib.request.Request(uri, headers={"User-Agent": "MTG-CardKeeper/1.0"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        with open(BULK_CACHE, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    elapsed = time.time() - start
    size_mb = os.path.getsize(BULK_CACHE) / 1024 / 1024
    print(f"  下载完成: {size_mb:.1f} MB ({elapsed:.1f}s)")


def extract_sets(card_names_set: set) -> tuple[dict, dict]:
    """从 bulk data 中提取指定卡牌的系列信息。

    流式读取 JSONL.gz，每行一个 JSON 对象。
    匹配策略（处理双面/分割/Meld 牌）：
      1. 精确名匹配
      2. 数据库中 " / " 在 Scryfall 为 " // "（旧 split card 命名差异）
      3. 数据库只存了单面名，匹配 bulk data 中 "{face} // ..." 的双面牌

    Returns:
        (result, sets_index)
        result: {card_name: [{"code": "roe", "name": "Rise of the Eldrazi"}, ...]}
        sets_index: {set_code: set_name}
    """
    print(f"\n流式解析 bulk data...")
    # 构建查找表：
    #   exact_lookup: 精确匹配名 -> 原始 db_name 列表
    #   这样支持一张 db 卡名通过多种方式（精确/斜杠替换/单面）命中多个 Scryfall 完整名
    exact_lookup = {}  # {scryfall_full_name: [db_name, ...]}
    for db_name in card_names_set:
        # 1. 精确
        exact_lookup.setdefault(db_name, []).append(db_name)
        # 2. " / " -> " // "
        if " / " in db_name:
            alt = db_name.replace(" / ", " // ")
            exact_lookup.setdefault(alt, []).append(db_name)

    result = {name: [] for name in card_names_set}
    sets_index = {}  # {set_code: set_name}
    # 单面匹配的卡需要二次扫描（双面牌的背面），先收集
    face_candidates = {}  # {face_name: [(db_name, scryfall_full_name), ...]}
    total_lines = 0
    matched = 0
    start = time.time()

    with gzip.open(BULK_CACHE, "rt", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            if total_lines % 50000 == 0:
                print(f"  进度: {total_lines} 行, 匹配 {matched} 张卡...")

            try:
                card = json.loads(line)
            except json.JSONDecodeError:
                continue

            name = card.get("name", "")
            if not name:
                continue

            set_code = card.get("set", "")
            set_name = card.get("set_name", "")
            if not set_code:
                continue

            # 更新系列索引（所有卡都更新，不限于匹配的卡）
            if set_code not in sets_index:
                sets_index[set_code] = set_name

            # 1. 精确 / 斜杠替换匹配
            if name in exact_lookup:
                for db_name in exact_lookup[name]:
                    _add_set(result[db_name], set_code, set_name)
                    matched += 1
                continue  # 同一张 Scryfall 卡不会同时是精确匹配和单面匹配候选

            # 2. 单面匹配（双面牌：数据库只存了其中一面）
            if " // " in name:
                faces = [f.strip() for f in name.split(" // ")]
                for face in faces:
                    if face in card_names_set and face not in exact_lookup:
                        # 数据库中存在此单面名，且未被精确匹配处理
                        _add_set(result[face], set_code, set_name)
                        matched += 1

    elapsed = time.time() - start
    print(f"  完成: {total_lines} 行, 匹配 {matched} 次印刷, {elapsed:.1f}s")
    return result, sets_index


def _add_set(target_list: list, code: str, name: str):
    """去重添加系列到列表"""
    for s in target_list:
        if s["code"] == code:
            return
    target_list.append({"code": code, "name": name})


def main():
    print("=" * 60)
    print("从 Scryfall Bulk Data 提取卡牌系列信息")
    print("=" * 60)

    # 1. 加载数据库，获取所有卡名
    with open(DEPLOY_DB, "r", encoding="utf-8") as f:
        db = json.load(f)

    card_names = {k for k in db.keys() if not k.startswith("__")}
    print(f"数据库卡牌数: {len(card_names)}")

    # 2. 下载 bulk data
    print("\n--- 下载 Bulk Data ---")
    uri = get_bulk_download_uri()
    download_bulk(uri)

    # 3. 流式提取系列信息
    sets_map, sets_index = extract_sets(card_names)

    # 4. 更新数据库
    print("\n--- 更新数据库 ---")
    updated = 0
    for name in card_names:
        card_sets = sets_map.get(name, [])
        set_codes = [s["code"] for s in card_sets]
        db[name]["sets"] = set_codes
        if set_codes:
            updated += 1

    with open(DEPLOY_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print(f"✅ 数据库已更新: {DEPLOY_DB}")

    # 5. 保存系列索引
    with open(SETS_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(sets_index, f, ensure_ascii=False, indent=2)
    print(f"✅ 系列索引已保存: {SETS_INDEX_PATH}")

    # 6. 统计
    has_sets = sum(1 for n in card_names if db[n].get("sets"))
    all_counts = [len(db[n].get("sets", [])) for n in card_names]
    avg_sets = sum(all_counts) / max(len(all_counts), 1)
    max_idx = max(range(len(all_counts)), key=lambda i: all_counts[i])
    max_name = list(card_names)[max_idx]
    max_count = all_counts[max_idx]

    print(f"\n--- 统计 ---")
    print(f"  有系列数据: {has_sets} / {len(card_names)}")
    print(f"  系列总数: {len(sets_index)}")
    print(f"  平均系列数/卡: {avg_sets:.1f}")
    print(f"  最多系列: {max_name} ({max_count} 个系列)")


if __name__ == "__main__":
    main()
