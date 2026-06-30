# MortalCoach App

这里是 MortalCoach 的应用本体。普通用户不需要直接进入这个目录启动。

推荐从仓库根目录运行：

```powershell
.\Start-MortalCoach.bat
```

环境检查：

```powershell
.\Start-MortalCoach.bat doctor
```

## 开发者运行方式

如果只想启动本地 Web 服务，可以进入本目录运行：

```powershell
python app.py
```

然后访问：

```text
http://127.0.0.1:8766
```

如果想直接调试 Electron：

```powershell
npm install
npm run desktop
```

## 依赖

主流程需要：

- Python 3.10+
- Node.js + npm
- Electron，首次运行会通过 `npm install` 安装

`requirements.txt` 当前没有强制 Python 第三方依赖。Playwright 只用于旧的浏览器兜底流程，默认桌面流程不需要它。

如需旧流程：

```powershell
python -m pip install playwright
python -m playwright install chromium
```

## 数据位置

本地数据保存在：

```text
mortalcoach/data/
```

主要包括：

- `mortalcoach.sqlite3`：牌谱库、复盘记录、训练档案
- `electron-profile/`：Electron 内嵌网页的本地配置和缓存
- `backups/`：隐藏维护接口生成的备份

这些都是个人数据，已经在 `.gitignore` 中排除。

## 当前主流程

1. 在总览页粘贴雀魂或天凤牌谱链接。
2. 选择 Mortal 模型版本。
3. 点击“开始 Mortal 分析并保存”。
4. 在软件内嵌的官方 Mortal 页面完成分析。
5. MortalCoach 保存结果和棋盘复盘数据。
6. 在牌谱库中重新打开时，不需要再跑一次官方分析。

## 牌谱库

牌谱库支持：

- 按雀魂 / 天凤筛选
- 按最近分析、rating、错误数、最大 Q 差排序
- 搜索标题、链接、标签
- 点击标题直接重命名
- 删除不需要保留的牌谱

## 复盘界面

复盘界面以 KillerDucky 棋盘为主体：

- 默认按牌局顺序复盘错误
- 可选择全部错误、Top 5、Top 10
- 棋盘内上一错误 / 下一错误会同步右侧 MortalCoach 信息栏
- 支持记录掌握状态和复盘备注
- 支持深色 / 浅色主题

## 训练档案

当前接入雀魂公开统计入口，按段位场展示主要数据，例如对局数、平均顺位、安定段位、排名分布等。

天凤训练档案入口已预留，后续再接入天凤统计数据。

## 本地引擎说明

Mortal 开源代码不包含官方训练权重。为了让普通用户开箱可用，当前默认路线是使用官方 Mortal 网页分析，而不是要求用户本地部署 Mortal。

旧的本地 `mjai-reviewer` / `tensoul` 配置代码仍保留在代码层，但不是默认发布路径。需要本地引擎的用户应自行安装：

- `mjai-reviewer`
- Mortal 本体和模型权重
- 可用的 Mahjong Soul 日志转换工具

## 文件结构

```text
mortalcoach/
  app.py                 本地 HTTP 服务和 API
  db.py                  SQLite 数据层
  official_runner.py     旧 Playwright 官方网页流程
  reviewer_runner.py     旧本地 mjai-reviewer 流程
  analysis.py            结构化复盘 JSON 解析
  link_utils.py          输入链接/JSON/HTML 判定
  desktop/               Electron 主进程
  scripts/               环境检查和旧流程辅助脚本
  static/                MortalCoach 前端
  samples/               示例复盘 JSON
```

## 发布检查

```powershell
python -m py_compile app.py db.py scripts/doctor.py
npm run doctor
```

如果有 Node：

```powershell
node --check static/app.js
node --check ..\killer_mortal_gui\index.js
node --check ..\killer_mortal_gui\boot.js
```
