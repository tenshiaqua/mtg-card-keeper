# MTG 卡牌保留价值查询

🔗 **在线访问**：https://tenshiaqua.github.io/mtg-card-keeper/

综合 Modern / Standard / Pauper 构筑赛制 + EDHREC EDH 使用数据，判断万智牌卡牌是否值得保留。

## 📦 仓库结构

```
├── index.html / app.js / card_database.json   ← 前端静态文件（Pages 直接服务）
├── .github/workflows/weekly-update.yml         ← 每周自动更新工作流
├── scripts/                                    ← 数据抓取与构建代码
│   ├── mtgtop8_scraper/                        ← mtgtop8 抓取器（纯标准库）
│   ├── card_keeper/                            ← 数据库合并与推荐逻辑
│   ├── build_deploy.py                         ← 构建+归档+趋势计算
│   └── prune_history.py                        ← 清理旧快照
└── history/                                    ← 每周数据快照（保留12周）
```

## 🔄 自动更新机制

### 构筑数据（每周一自动）

GitHub Actions 每周一 11:00（北京时间）自动运行：

1. 抓取 mtgtop8 最近 3 个月的 Standard / Modern / Pauper 上位数据
2. 归档当前数据库到 `history/snapshot_YYYYMMDD.json`
3. 重建数据库，对比上周计算趋势（↑上升 / ↓下降 / →持平 / ✨新增）
4. 提交推送，GitHub Pages 自动重建

也可在仓库 Actions 页面手动触发（`workflow_dispatch`）。

### EDHREC 数据（手动月更）

EDHREC 有 Cloudflare 保护无法自动抓取，需手动更新：

```bash
# 1. 本地启动 card_keeper 服务
python -m card_keeper.server --port 8080

# 2. 用浏览器 MCP 采集 EDHREC /top/{color} 页面数据
#    （通过 /api/edh 端点写入 edhrec_cache.json）

# 3. 将更新后的 edhrec_cache.json 复制到仓库
copy edhrec_cache.json scripts\card_keeper\data\edhrec_cache.json

# 4. 提交推送
git add scripts/card_keeper/data/edhrec_cache.json
git commit -m "data: 月度更新 EDHREC 数据"
git push
```

下次 Actions 运行时会自动合并新的 EDH 数据。

## 🛠️ 本地构建

```bash
# 手动构建部署数据库（含趋势计算）
python scripts/build_deploy.py

# 本地预览
python -m http.server 8080
# 浏览器访问 http://localhost:8080/
```

## 📊 数据来源

| 数据源 | 内容 | 卡牌数 |
|--------|------|--------|
| mtgtop8.com | Standard/Modern/Pauper 最近3个月上位 | ~1839 |
| EDHREC | EDH top 卡使用统计 | ~2528 |
| Scryfall | 卡牌信息（稀有度/颜色/类型/费用） | 缓存递增 |
| Scryfall | 中文卡名 | 缓存递增 |

## 🎯 功能说明

输入卡牌英文名或中文名，显示：

1. **保留建议**（颜色标识）
   - 🟢 强烈保留：构筑 + EDH 双修
   - 🟢 保留：构筑 + EDH 偶用
   - 🟡 构筑专用：仅构筑使用
   - 🟡 EDH专用：仅 EDH 使用
   - 🟠 可保留：EDH 偶用
   - 🔴 可不保留：都不用

2. **构筑赛制使用**（最近 3 个月上位卡组 + 趋势指示）

3. **EDH 使用情况**（EDHREC 数据 + 趋势指示）

## ⚡ 性能

- 数据库约 1MB，首次加载 1-2 秒
- 加载后所有查询在浏览器本地完成，响应 < 10ms
- 无需服务器，GitHub Pages 永久免费
