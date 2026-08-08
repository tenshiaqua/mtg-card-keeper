# MTG 卡牌保留价值查询 - GitHub Pages 部署

## 📦 部署文件

部署目录包含 3 个文件，总计约 1MB：

| 文件 | 大小 | 说明 |
|---|---|---|
| `index.html` | ~7 KB | 前端页面 |
| `app.js` | ~8 KB | 前端查询引擎 |
| `card_database.json` | ~1 MB | 压缩版卡牌数据库（4036 张卡） |

## 🚀 部署到 GitHub Pages

### 方法一：新建仓库部署（推荐）

1. **在 GitHub 创建新仓库**（如 `mtg-card-keeper`，设为 Public）

2. **上传 deploy 目录内容**
   ```bash
   cd e:\Codes\MTG\card_keeper\deploy
   git init
   git add .
   git commit -m "MTG 卡牌保留价值查询"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/mtg-card-keeper.git
   git push -u origin main
   ```

3. **开启 GitHub Pages**
   - 进入仓库 → Settings → Pages
   - Source 选择 **Deploy from a branch**
   - Branch 选择 `main` / `(root)`
   - 点击 Save

4. **等待 1-2 分钟**，访问：
   ```
   https://<你的用户名>.github.io/mtg-card-keeper/
   ```

### 方法二：部署到已有仓库的子目录

如果不想新建仓库，可以放到已有仓库的子目录：

1. 将 `deploy/` 目录内容复制到仓库的 `docs/` 或 `mtg-card-keeper/` 目录
2. Settings → Pages → Source 选 main 分支
3. 如果放在子目录，需要设置仓库名为 `<用户名>.github.io` 或使用自定义域名

> ⚠️ 注意：GitHub Pages 默认只服务根目录。如果放在子目录，URL 会包含子目录路径。

## 🔄 更新数据

当有新的构筑数据或 EDH 数据时，重新生成部署文件：

```bash
# 1. 重建数据库（合并所有数据源）
python -m card_keeper.build_database

# 2. 生成部署目录
python -m card_keeper.deploy

# 3. 将 deploy/ 内容重新上传到 GitHub
cd e:\Codes\MTG\card_keeper\deploy
git add card_database.json
git commit -m "更新卡牌数据库"
git push
```

GitHub Pages 会在 1-2 分钟内自动更新。

## 🛠️ 本地测试

部署前可以本地测试：

```bash
# 进入 deploy 目录
cd e:\Codes\MTG\card_keeper\deploy

# 启动简易 HTTP 服务器
python -m http.server 8081

# 浏览器访问
# http://localhost:8081/
```

## 📊 数据库统计

- 总卡牌数：4036 张
- 构筑赛制数据：1839 张（Modern / Standard / Pauper 最近 3 个月上位）
- EDHREC EDH 数据：2528 张
- 中文卡名：1838 张

## 🎯 功能说明

输入卡牌英文名或中文名，显示：

1. **保留建议**（颜色标识）
   - 🟢 强烈保留：构筑 + EDH 双修
   - 🟢 保留：构筑 + EDH 偶用
   - 🟡 构筑专用：仅构筑使用
   - 🟡 EDH专用：仅 EDH 使用
   - 🟠 可保留：EDH 偶用
   - 🔴 可不保留：都不用

2. **构筑赛制使用**（最近 3 个月上位卡组）
   - Standard / Modern / Pauper 主牌 + 备牌数量

3. **EDH 使用情况**（EDHREC 数据）
   - 使用卡组数、包含率、Salt 值、等级

## ⚡ 性能

- 数据库约 1MB，首次加载 1-2 秒
- 加载后所有查询在浏览器本地完成，响应 < 10ms
- 无需服务器，永久免费在线
