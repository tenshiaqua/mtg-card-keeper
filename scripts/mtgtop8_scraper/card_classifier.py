"""
卡牌分类模块
使用 Scryfall API 获取卡牌稀有度/颜色/类型等信息，并按维度分类。
支持本地缓存（card_cache.json），定期更新时避免重复查询 Scryfall。
"""

import json
import time
import os
import urllib.request
import urllib.parse
import urllib.error
from collections import defaultdict
from typing import Optional

SCRYFALL_API = "https://api.scryfall.com"
_last_scryfall_time = 0.0

# 稀有度排序（输出表格时按此顺序）
RARITY_ORDER = ["mythic", "rare", "uncommon", "common", "special", "bonus", "unknown"]
RARITY_CN = {
    "mythic": "秘稀", "rare": "稀有", "uncommon": "非普通",
    "common": "普通", "special": "特殊", "bonus": "额外", "unknown": "未知",
}

# 颜色排序
COLOR_ORDER = ["W", "U", "B", "R", "G", "Colorless", "Multicolor"]
COLOR_CN = {
    "W": "白色", "U": "蓝色", "B": "黑色", "R": "红色", "G": "绿色",
    "Colorless": "无色", "Multicolor": "多色",
}

# 类型分类映射（按优先级顺序检查）
TYPE_CATEGORIES = {
    "Creature": ["Creature"],
    "Planeswalker": ["Planeswalker"],
    "Battle": ["Battle"],
    "Artifact": ["Artifact"],
    "Enchantment": ["Enchantment"],
    "Instant": ["Instant"],
    "Sorcery": ["Sorcery"],
    "Kindred": ["Kindred", "Tribal"],
    "Land": ["Land"],
}
TYPE_CN = {
    "Creature": "生物", "Planeswalker": "鹏洛客", "Battle": "战役",
    "Artifact": "神器", "Enchantment": "结界", "Instant": "瞬间",
    "Sorcery": "法术", "Kindred": "宗族", "Land": "地", "Other": "其他",
}


def _rate_limit():
    """Scryfall API 速率限制 (100ms)"""
    global _last_scryfall_time
    elapsed = time.time() - _last_scryfall_time
    if elapsed < 0.1:
        time.sleep(0.1 - elapsed)
    _last_scryfall_time = time.time()


def _scryfall_post(endpoint: str, data: dict) -> Optional[dict]:
    """Scryfall API POST 请求"""
    _rate_limit()
    url = f"{SCRYFALL_API}/{endpoint}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MTG-Analysis/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(5)
        return None
    except Exception:
        return None


def _scryfall_get(endpoint: str, params: dict = None) -> Optional[dict]:
    """Scryfall API GET 请求"""
    _rate_limit()
    url = f"{SCRYFALL_API}/{endpoint}"
    if params:
        url += f"?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MTG-Analysis/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def classify_color(colors: list) -> str:
    """分类卡牌颜色: 单色返回色组字母，无色返回 Colorless，多色返回 Multicolor"""
    if not colors:
        return "Colorless"
    if len(colors) == 1:
        return colors[0]
    return "Multicolor"


def classify_type(type_line: str) -> str:
    """根据 type_line 分类卡牌主类型"""
    if not type_line:
        return "Other"
    type_lower = type_line.lower()
    for category, keywords in TYPE_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in type_lower:
                return category
    return "Other"


def _build_card_info(card: dict) -> dict:
    """从 Scryfall 卡牌数据构建标准化的卡牌信息字典"""
    # 双面牌：顶层没有 type_line 时取正面
    if "card_faces" in card and "type_line" not in card:
        front = card["card_faces"][0]
        type_line = front.get("type_line", "")
        mana_cost = front.get("mana_cost", "")
    else:
        type_line = card.get("type_line", "")
        mana_cost = card.get("mana_cost", "")

    colors = card.get("colors", [])
    rarity = card.get("rarity", "unknown")

    return {
        "name": card.get("name", ""),
        "rarity": rarity,
        "colors": colors,
        "color_category": classify_color(colors),
        "type_line": type_line,
        "type_category": classify_type(type_line),
        "cmc": card.get("cmc", 0),
        "mana_cost": mana_cost,
        "set": card.get("set", ""),
        "set_name": card.get("set_name", ""),
        "is_basic_land": "Basic" in type_line and "Land" in type_line,
    }


def batch_get_card_info(card_names: list[str], cache: dict = None) -> dict[str, dict]:
    """
    批量获取卡牌信息（Scryfall collection API），优先用缓存。

    Args:
        card_names: 卡牌英文名称列表
        cache: 已有缓存 {name: info}，命中的不再查询

    Returns:
        {card_name: card_info_dict, ...}（包含缓存 + 新查询的结果）
    """
    if cache is None:
        cache = {}

    results = dict(cache)
    # 找出未命中的
    uncached = [n for n in card_names if n not in results]
    if not uncached:
        print(f"    全部 {len(card_names)} 张卡牌命中缓存")
        return results

    print(f"    缓存命中 {len(card_names) - len(uncached)} 张，需查询 {len(uncached)} 张")
    batch_size = 75

    for i in range(0, len(uncached), batch_size):
        batch = uncached[i:i + batch_size]
        end = min(i + batch_size, len(uncached))
        print(f"    查询 Scryfall: {i + 1}-{end}/{len(uncached)}")

        identifiers = [{"name": n} for n in batch]
        data = None
        for attempt in range(3):
            data = _scryfall_post("cards/collection", {"identifiers": identifiers})
            if data is not None:
                break
            wait = 5 * (attempt + 1)
            print(f"      重试 ({attempt + 1}/3)，等待 {wait}s ...")
            time.sleep(wait)

        if data:
            for card in data.get("data", []):
                info = _build_card_info(card)
                results[info["name"]] = info
                # 同步缓存原始 key（防止大小写/写法差异）
            # 未找到的卡牌单独兜底查询
            for nf in data.get("not_found", []):
                nf_name = nf.get("name", "")
                if not nf_name:
                    continue
                single = _scryfall_get("cards/named", {"fuzzy": nf_name})
                if single:
                    info = _build_card_info(single)
                    results[info["name"]] = info
                    results[nf_name] = info
                else:
                    results[nf_name] = _unknown_card_info(nf_name)
        else:
            # 整批失败，全部置为 unknown
            for n in batch:
                if n not in results:
                    results[n] = _unknown_card_info(n)

        if end < len(uncached):
            time.sleep(0.5)

    return results


def _unknown_card_info(name: str) -> dict:
    return {
        "name": name,
        "rarity": "unknown",
        "colors": [],
        "color_category": "Colorless",
        "type_line": "Unknown",
        "type_category": "Other",
        "cmc": 0,
        "mana_cost": "",
        "set": "",
        "set_name": "",
        "is_basic_land": False,
    }


def classify_cards(card_counts: dict[str, int], card_info: dict[str, dict]) -> dict:
    """
    按稀有度/颜色/类型三个维度分类卡牌（已排除基本地）。

    card_counts 的 key 可能带 " [SB]" 后缀表示备牌数量。
    """
    by_rarity = defaultdict(list)
    by_color = defaultdict(list)
    by_type = defaultdict(list)

    total_cards = 0
    total_copies = 0

    for key, count in card_counts.items():
        clean_name = key.replace(" [SB]", "")
        is_sideboard = key.endswith(" [SB]")
        info = card_info.get(clean_name) or card_info.get(key) or _unknown_card_info(clean_name)

        # 二次过滤基本地
        if info.get("is_basic_land") or clean_name in _BASIC_LANDS:
            continue

        entry = {
            "name": clean_name,
            "count": count,
            "is_sideboard": is_sideboard,
            "rarity": info["rarity"],
            "color_category": info["color_category"],
            "type_category": info["type_category"],
            "cmc": info["cmc"],
            "mana_cost": info["mana_cost"],
            "type_line": info["type_line"],
        }

        by_rarity[info["rarity"]].append(entry)
        by_color[info["color_category"]].append(entry)
        by_type[info["type_category"]].append(entry)

        total_cards += 1
        total_copies += count

    # 各分类内按使用数量降序
    for bucket in (by_rarity, by_color, by_type):
        for k in bucket:
            bucket[k].sort(key=lambda x: x["count"], reverse=True)

    def ordered(src: dict, order: list) -> dict:
        return {k: src[k] for k in order if k in src}

    return {
        "by_rarity": dict(by_rarity),
        "by_color": dict(by_color),
        "by_type": dict(by_type),
        "summary": {
            "total_cards": total_cards,
            "total_copies": total_copies,
            "rarity_stats": ordered(dict(by_rarity), RARITY_ORDER),
            "color_stats": ordered(dict(by_color), COLOR_ORDER),
            "type_stats": ordered(dict(by_type), list(TYPE_CATEGORIES.keys()) + ["Other"]),
        },
    }


# 基本地名称集合（与 scraper.py 保持一致）
_BASIC_LANDS = {
    "Plains", "Island", "Swamp", "Mountain", "Forest",
    "Wastes", "Snow-Covered Plains", "Snow-Covered Island",
    "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Forest",
}


# ============================================================
# 缓存读写
# ============================================================

def load_card_cache(filepath: str) -> dict:
    """加载卡牌信息本地缓存"""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_card_cache(filepath: str, cache: dict):
    """保存卡牌信息缓存"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def process_format_data(format_name: str, card_counts: dict[str, int],
                        cache: dict = None) -> tuple[dict, dict]:
    """
    处理单个赛制：查询卡牌信息并分类。

    Returns:
        (classified_result, updated_card_cache)
    """
    print(f"\n  [{format_name.upper()}] 处理卡牌数据...")
    clean_names = sorted({k.replace(" [SB]", "") for k in card_counts.keys()})
    print(f"    共 {len(clean_names)} 种不同卡牌")

    card_info = batch_get_card_info(clean_names, cache=cache or {})
    classified = classify_cards(card_counts, card_info)
    return classified, card_info
