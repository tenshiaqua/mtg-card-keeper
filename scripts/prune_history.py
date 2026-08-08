"""清理旧的历史快照，只保留最近 N 周。

用法：
    python scripts/prune_history.py            # 默认保留12周
    python scripts/prune_history.py --keep 8   # 保留8周
"""

import os
import sys


def main(keep=12):
    history_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "history",
    )
    if not os.path.isdir(history_dir):
        print("无 history 目录，跳过清理。")
        return

    files = sorted(
        f for f in os.listdir(history_dir) if f.startswith("snapshot_")
    )
    if len(files) <= keep:
        print(f"当前 {len(files)} 个快照，不超过保留数 {keep}，无需清理。")
        return

    to_delete = files[:-keep]
    for old_file in to_delete:
        os.remove(os.path.join(history_dir, old_file))
        print(f"🗑️  删除旧快照: {old_file}")
    print(f"已清理 {len(to_delete)} 个旧快照，保留最近 {keep} 个。")


if __name__ == "__main__":
    keep = 12
    if "--keep" in sys.argv:
        idx = sys.argv.index("--keep")
        if idx + 1 < len(sys.argv):
            keep = int(sys.argv[idx + 1])
    main(keep)
