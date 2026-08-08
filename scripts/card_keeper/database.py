"""
卡牌数据库合并与查询模块。

合并多个数据源为统一的卡牌数据库：
- mtgtop8 构筑赛制使用统计 (processed_*.json)
- EDHREC EDH 使用统计 (edhrec_cache.json)
- Scryfall 卡牌信息 (card_cache.json)
- 中文卡名 (chinese_cache.json)

提供 EDH 有用性判断和保留建议逻辑。
"""

import json
import os
from typing import Optional

# ============================================================
# 常量
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
MTGTOP8_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "mtgtop8_scraper", "data")

# EDH 等级
EDH_TIERS = {
    "core": {"label": "⭐ 核心", "color": "#ff6b6b"},
    "common": {"label": "✅ 常用", "color": "#51cf66"},
    "occasional": {"label": "⚠️ 偶用", "color": "#ffd43b"},
    "rare": {"label": "❌ 少用", "color": "#868e96"},
    "unknown": {"label": "❓ 未收录", "color": "#adb5bd"},
}

# 保留建议
RECOMMENDATIONS = {
    "keep_strong": {"label": "🟢 强烈保留", "color": "#2b8a3e"},
    "keep": {"label": "🟢 保留", "color": "#40c057"},
    "keep_constructed": {"label": "🟡 构筑专用", "color": "#fab005"},
    "keep_edh": {"label": "🟡 EDH专用", "color": "#fab005"},
    "maybe": {"label": "🟠 可保留", "color": "#fd7e14"},
    "drop": {"label": "🔴 可不保留", "color": "#e03131"},
}

# 稀有度中文
RARITY_CN = {
    "mythic": "秘稀", "rare": "稀有", "uncommon": "非普通",
    "common": "普通", "special": "特殊", "bonus": "额外", "unknown": "未知",
}

# 颜色中文
COLOR_CN = {
    "W": "白", "U": "蓝", "B": "黑", "R": "红", "G": "绿",
    "Colorless": "无色", "Multicolor": "多色",
}


# ============================================================
# 判断逻辑
# ============================================================

def classify_edh(num_decks: int, inclusion: float) -> str:
    """EDH 有用性等级判断。

    Returns: "core" / "common" / "occasional" / "rare" / "unknown"
    """
    if num_decks == 0 and inclusion == 0:
        return "unknown"
    if num_decks > 50000 or inclusion > 0.30:
        return "core"
    if num_decks > 5000 or inclusion > 0.05:
        return "common"
    if num_decks > 500 or inclusion > 0.01:
        return "occasional"
    return "rare"


def recommend(constructed_used: bool, edh_tier: str) -> str:
    """保留建议判断。

    Args:
        constructed_used: 构筑赛制是否使用过
        edh_tier: EDH 等级 (classify_edh 返回值)

    Returns: 建议key
    """
    edh_good = edh_tier in ("core", "common")
    edh_ok = edh_tier == "occasional"

    if constructed_used and edh_good:
        return "keep_strong"
    if constructed_used and edh_ok:
        return "keep"
    if constructed_used:
        return "keep_constructed"
    if edh_good:
        return "keep_edh"
    if edh_ok:
        return "maybe"
    return "drop"


# ============================================================
# 数据库
# ============================================================

class CardDatabase:
    """卡牌数据库：合并多源数据，提供查询接口"""

    def __init__(self):
        self.cards: dict[str, dict] = {}
        self._name_index: dict[str, str] = {}  # 小写卡名 → 原始卡名（搜索用）

    # ---------- 数据加载 ----------

    def load_mtgtop8(self, processed_path: str):
        """从 mtgtop8 processed_*.json 加载构筑赛制使用数据"""
        with open(processed_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for fmt_name, fmt_data in data.items():
            card_counts = fmt_data.get("card_counts", {})
            for key, count in card_counts.items():
                # 分离主牌和备牌
                is_sb = key.endswith(" [SB]")
                card_name = key.replace(" [SB]", "") if is_sb else key

                if card_name not in self.cards:
                    self.cards[card_name] = {
                        "name": card_name,
                        "chinese_name": "",
                        "rarity": "",
                        "colors": [],
                        "color_category": "",
                        "type_line": "",
                        "type_category": "",
                        "cmc": 0,
                        "constructed": {},
                        "edh": None,
                        "edh_tier": "unknown",
                        "recommendation": "",
                    }

                card = self.cards[card_name]
                if fmt_name not in card["constructed"]:
                    card["constructed"][fmt_name] = {"count": 0, "sideboard": 0}
                if is_sb:
                    card["constructed"][fmt_name]["sideboard"] += count
                else:
                    card["constructed"][fmt_name]["count"] += count

        # 计算保留建议（此时 edh_tier 默认 unknown）
        for card in self.cards.values():
            constructed_used = any(
                v["count"] > 0 or v["sideboard"] > 0
                for v in card["constructed"].values()
            )
            card["_constructed_used"] = constructed_used
            card["recommendation"] = recommend(constructed_used, card["edh_tier"])

    def load_edhrec(self, edhrec_cache: dict):
        """合并 EDHREC 缓存数据"""
        for name, edh_data in edhrec_cache.items():
            # 尝试匹配已有卡牌（精确匹配）
            if name in self.cards:
                card = self.cards[name]
            else:
                # 新卡（不在 mtgtop8 数据中）
                card = {
                    "name": name,
                    "chinese_name": "",
                    "rarity": edh_data.get("rarity", ""),
                    "colors": [],
                    "color_category": "",
                    "type_line": edh_data.get("primary_type", ""),
                    "type_category": "",
                    "cmc": 0,
                    "constructed": {},
                    "edh": None,
                    "edh_tier": "unknown",
                    "recommendation": "",
                }
                self.cards[name] = card

            num_decks = edh_data.get("num_decks", 0)
            potential_decks = edh_data.get("potential_decks", 0)
            inclusion = edh_data.get("inclusion", 0)
            if inclusion == 0 and potential_decks > 0:
                inclusion = num_decks / potential_decks

            card["edh"] = {
                "num_decks": num_decks,
                "potential_decks": potential_decks,
                "inclusion": round(inclusion, 6),
                "salt": edh_data.get("salt", 0),
            }
            card["edh_tier"] = classify_edh(num_decks, inclusion)

            # 如果 rarity 为空，用 EDHREC 的
            if not card["rarity"] and edh_data.get("rarity"):
                card["rarity"] = edh_data["rarity"]

            # 重新计算建议
            constructed_used = card.get("_constructed_used", False)
            card["recommendation"] = recommend(constructed_used, card["edh_tier"])

    def load_card_cache(self, card_cache: dict):
        """合并 Scryfall 卡牌信息"""
        for name, info in card_cache.items():
            if name in self.cards:
                card = self.cards[name]
                if not card["rarity"]:
                    card["rarity"] = info.get("rarity", "")
                card["colors"] = info.get("colors", [])
                card["color_category"] = info.get("color_category", "")
                card["type_line"] = info.get("type_line", card.get("type_line", ""))
                card["type_category"] = info.get("type_category", "")
                card["cmc"] = info.get("cmc", 0)
                card["is_basic_land"] = info.get("is_basic_land", False)
            else:
                # 添加不在 mtgtop8 但在 card_cache 中的卡
                self.cards[name] = {
                    "name": name,
                    "chinese_name": "",
                    "rarity": info.get("rarity", ""),
                    "colors": info.get("colors", []),
                    "color_category": info.get("color_category", ""),
                    "type_line": info.get("type_line", ""),
                    "type_category": info.get("type_category", ""),
                    "cmc": info.get("cmc", 0),
                    "is_basic_land": info.get("is_basic_land", False),
                    "constructed": {},
                    "edh": None,
                    "edh_tier": "unknown",
                    "recommendation": "",
                }

    def load_chinese_names(self, chinese_cache: dict):
        """合并中文卡名"""
        for name, cn_name in chinese_cache.items():
            if name in self.cards:
                self.cards[name]["chinese_name"] = cn_name

    def finalize_recommendations(self):
        """所有数据源加载完成后，统一计算所有卡牌的保留建议。

        解决 load_card_cache 新增的卡牌没有 recommendation 的问题。
        """
        for card in self.cards.values():
            constructed_used = any(
                v.get("count", 0) > 0 or v.get("sideboard", 0) > 0
                for v in card.get("constructed", {}).values()
            )
            card["_constructed_used"] = constructed_used
            card["recommendation"] = recommend(constructed_used, card.get("edh_tier", "unknown"))

    def build_index(self):
        """构建搜索索引"""
        self._name_index = {}
        for name in self.cards:
            self._name_index[name.lower()] = name

    # ---------- 查询 ----------

    def get_card(self, name: str) -> Optional[dict]:
        """获取单张卡牌完整信息"""
        # 精确匹配
        if name in self.cards:
            return self._format_card(self.cards[name])
        # 大小写不敏感匹配
        if name.lower() in self._name_index:
            return self._format_card(self.cards[self._name_index[name.lower()]])
        return None

    def search(self, query: str, limit: int = 15) -> list[dict]:
        """模糊搜索卡名（英文 + 中文）"""
        query = query.strip().lower()
        if not query:
            return []

        results = []
        for name, card in self.cards.items():
            score = 0
            name_lower = name.lower()
            cn = card.get("chinese_name", "")

            # 精确匹配
            if name_lower == query:
                score = 100
            # 前缀匹配
            elif name_lower.startswith(query):
                score = 80
            # 包含匹配
            elif query in name_lower:
                score = 60
            # 中文匹配
            elif cn and query in cn.lower():
                score = 50
            # 模糊匹配（每个词都包含）
            elif all(q in name_lower for q in query.split()):
                score = 40

            if score > 0:
                results.append((score, name))

        results.sort(key=lambda x: (-x[0], x[1]))
        return [self._format_card(self.cards[n]) for _, n in results[:limit]]

    def stats(self) -> dict:
        """数据库统计信息"""
        total = len(self.cards)
        has_constructed = sum(1 for c in self.cards.values()
                              if any(v["count"] > 0 or v["sideboard"] > 0
                                     for v in c["constructed"].values()))
        has_edh = sum(1 for c in self.cards.values() if c["edh"] is not None)
        has_chinese = sum(1 for c in self.cards.values() if c.get("chinese_name"))

        tier_counts = {}
        for c in self.cards.values():
            t = c["edh_tier"]
            tier_counts[t] = tier_counts.get(t, 0) + 1

        rec_counts = {}
        for c in self.cards.values():
            r = c["recommendation"]
            rec_counts[r] = rec_counts.get(r, 0) + 1

        return {
            "total_cards": total,
            "has_constructed": has_constructed,
            "has_edh": has_edh,
            "has_chinese_name": has_chinese,
            "edh_tier_distribution": tier_counts,
            "recommendation_distribution": rec_counts,
        }

    # ---------- 内部工具 ----------

    def _format_card(self, card: dict) -> dict:
        """格式化卡牌数据用于 API 返回（移除内部字段）"""
        result = {k: v for k, v in card.items() if not k.startswith("_")}
        # 添加中文标签
        result["rarity_cn"] = RARITY_CN.get(card.get("rarity", ""), card.get("rarity", ""))
        result["color_cn"] = COLOR_CN.get(card.get("color_category", ""),
                                          card.get("color_category", ""))
        edh_tier = card.get("edh_tier", "unknown")
        result["edh_tier_label"] = EDH_TIERS.get(edh_tier, EDH_TIERS["unknown"])["label"]
        rec = card.get("recommendation", "drop")
        result["recommendation_label"] = RECOMMENDATIONS.get(rec, RECOMMENDATIONS["drop"])["label"]
        result["recommendation_color"] = RECOMMENDATIONS.get(rec, RECOMMENDATIONS["drop"])["color"]
        return result

    # ---------- 保存/加载 ----------

    def save(self, path: str):
        """保存完整数据库到 JSON"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 移除内部字段
        clean = {}
        for name, card in self.cards.items():
            clean[name] = {k: v for k, v in card.items() if not k.startswith("_")}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)

    def load(self, path: str):
        """从 JSON 加载完整数据库"""
        with open(path, "r", encoding="utf-8") as f:
            self.cards = json.load(f)
        self.build_index()


# ============================================================
# 构建入口
# ============================================================

def find_latest_file(directory: str, prefix: str, suffix: str = ".json") -> Optional[str]:
    """找目录下最新的 prefix*suffix 文件"""
    if not os.path.isdir(directory):
        return None
    files = [f for f in os.listdir(directory)
             if f.startswith(prefix) and f.endswith(suffix)]
    if not files:
        return None
    files.sort()
    return os.path.join(directory, files[-1])


def build_database() -> CardDatabase:
    """从所有数据源构建完整数据库"""
    db = CardDatabase()

    # 1. mtgtop8 构筑数据
    processed_path = find_latest_file(MTGTOP8_DATA_DIR, "processed_")
    if processed_path:
        print(f"加载构筑数据: {processed_path}")
        db.load_mtgtop8(processed_path)
        print(f"  构筑卡牌: {len(db.cards)} 种")
    else:
        print("⚠ 未找到 mtgtop8 processed_*.json")

    # 2. EDHREC 缓存
    edhrec_path = os.path.join(DATA_DIR, "edhrec_cache.json")
    if os.path.exists(edhrec_path):
        print(f"加载 EDHREC 缓存: {edhrec_path}")
        with open(edhrec_path, "r", encoding="utf-8") as f:
            edhrec_cache = json.load(f)
        db.load_edhrec(edhrec_cache)
        print(f"  EDHREC 数据: {len(edhrec_cache)} 张")
    else:
        print("⚠ 未找到 edhrec_cache.json（EDH 数据为空）")

    # 3. Scryfall 卡牌信息
    card_cache_path = os.path.join(MTGTOP8_DATA_DIR, "card_cache.json")
    if os.path.exists(card_cache_path):
        print(f"加载 Scryfall 缓存: {card_cache_path}")
        with open(card_cache_path, "r", encoding="utf-8") as f:
            card_cache = json.load(f)
        before = len(db.cards)
        db.load_card_cache(card_cache)
        print(f"  Scryfall 卡牌: {len(card_cache)} 张（新增 {len(db.cards) - before} 种）")

    # 4. 中文卡名
    cn_cache_path = os.path.join(MTGTOP8_DATA_DIR, "chinese_cache.json")
    if os.path.exists(cn_cache_path):
        print(f"加载中文卡名: {cn_cache_path}")
        with open(cn_cache_path, "r", encoding="utf-8") as f:
            cn_cache = json.load(f)
        db.load_chinese_names(cn_cache)
        print(f"  中文卡名: {len(cn_cache)} 张")

    # 5. 统一计算保留建议（确保所有卡牌都有 recommendation）
    db.finalize_recommendations()

    # 6. 构建索引
    db.build_index()
    print(f"\n数据库总计: {len(db.cards)} 种卡牌")
    return db
