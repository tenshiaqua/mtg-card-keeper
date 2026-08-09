"""压缩部署数据库：移除可计算字段 + 无缩进输出。

只压缩 card_database.json，不删除其他文件。
可从仓库根目录或 card_keeper/ 目录运行。
"""

import json
import os
import sys

# 尝试找到 card_database.json
# 1. 当前目录（仓库根目录 / deploy 目录）
# 2. ../card_database.json（如果脚本在 scripts/ 下）
# 3. ../../card_database.json（如果脚本在 scripts/card_keeper/ 下）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CANDIDATE_PATHS = [
    os.path.join(os.getcwd(), "card_database.json"),           # 当前工作目录
    os.path.join(SCRIPT_DIR, "card_database.json"),            # 脚本所在目录
    os.path.join(SCRIPT_DIR, "..", "card_database.json"),      # 上一级
    os.path.join(SCRIPT_DIR, "..", "..", "card_database.json"),# 上两级
]

DB_PATH = None
for p in CANDIDATE_PATHS:
    if os.path.exists(p):
        DB_PATH = os.path.abspath(p)
        break

STRIP_FIELDS = ("edh_tier", "recommendation", "is_basic_land", "_constructed_used")


def main():
    global DB_PATH
    if not DB_PATH:
        print(f"❌ 未找到 card_database.json")
        print(f"   搜索路径: {CANDIDATE_PATHS}")
        sys.exit(1)

    src_size = os.path.getsize(DB_PATH)

    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 移除可计算字段
    stripped = 0
    for card in data.values():
        for field in STRIP_FIELDS:
            if field in card:
                del card[field]
                stripped += 1

    # 无缩进压缩输出
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    dst_size = os.path.getsize(DB_PATH)
    ratio = (1 - dst_size / src_size) * 100

    print(f"✅ 压缩 card_database.json: {DB_PATH}")
    print(f"   {src_size / 1024:.0f} KB → {dst_size / 1024:.0f} KB (节省 {ratio:.0f}%)")
    print(f"   移除字段: {stripped} 个")
    print(f"   卡牌总数: {len(data)} 张")


if __name__ == "__main__":
    main()
