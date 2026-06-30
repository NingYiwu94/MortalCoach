# MortalCoach

MortalCoach 是一个本地麻将复盘管理软件。它的目标不是重新训练 Mortal，也不是要求普通玩家准备模型权重，而是把官方 Mortal / KillerDucky 的分析结果保存、整理、复盘起来。

当前主流程：

1. 粘贴雀魂或天凤牌谱链接。
2. MortalCoach 在软件内嵌官方 Mortal 页面提交分析。
3. 分析完成后保存结果、rating、错误列表和棋盘复盘数据。
4. 在本地牌谱库中管理所有复盘。
5. 用 KillerDucky 棋盘界面复盘，并支持 Top 5 / Top 10 错误筛选。

## 快速开始

环境要求：

- Windows 10/11
- Python 3.10+
- Node.js 20+ 或 22+，需自带 `npm`

启动：

```powershell
git clone <your-repo-url>
cd mortalreviewer
.\Start-MortalCoach.bat
```

第一次启动时，`MortalCoach.bat` 会在 `mortalcoach/` 下自动运行 `npm install` 安装 Electron。之后会打开桌面窗口。

如果启动失败，可运行：

```powershell
cd mortalcoach
.\MortalCoach.bat doctor
```

或使用浏览器模式：

```powershell
cd mortalcoach
python app.py
```

然后打开：

```text
http://127.0.0.1:8766
```

## 目录结构

```text
mortalreviewer/
  Start-MortalCoach.bat       一键启动入口
  README.md                   项目说明
  PROJECT_DIRECTION.md         产品方向说明
  docs/                       设计和维护文档
  killer_mortal_gui/          KillerDucky 棋盘复盘 UI，本项目做了嵌入适配
  mortalcoach/                MortalCoach 本体
```

`mortalcoach/data/` 会在首次运行时自动创建，用来保存 SQLite 数据库、缓存和本地浏览器配置。这个目录包含个人复盘数据，不应提交到 Git。

## 功能概览

- 软件内提交官方 Mortal 分析
- 保存已分析牌谱，避免重复跑同一份复盘
- 牌谱库支持搜索、筛选、排序、删除和直接重命名
- 复盘趋势图显示 rating 变化
- 训练档案支持雀魂公开统计同步入口，天凤入口已预留
- 复盘界面使用 KillerDucky 棋盘 UI
- 支持深色 / 浅色主题
- 复盘时可切换全部错误、Top 5、Top 10
- 右侧复盘栏会跟随棋盘里的上一错误 / 下一错误同步

## 重要说明

Mortal 开源代码本身不附带官方训练好的模型权重。MortalCoach 当前默认依赖官方 Mortal 网页完成分析，这样普通玩家无需配置本地模型。

本项目不会保存你的雀魂或天凤账号密码。官方分析流程在内嵌网页中完成；如遇到官方站点的人机验证，需要在窗口内手动完成。

## 第三方项目

MortalCoach 集成并适配了 KillerDucky 的 `killer_mortal_gui`：

- 上游项目：<https://github.com/killerducky/killer_mortal_gui>
- 许可证：MIT，保留在 `killer_mortal_gui/LICENSE`

官方 Mortal / mjai-reviewer：

- <https://mjai.ekyu.moe/>
- <https://github.com/Equim-chan/mjai-reviewer>
- <https://github.com/Equim-chan/Mortal>

## 发布前检查

```powershell
cd mortalcoach
.\MortalCoach.bat doctor
python -m py_compile app.py db.py scripts/doctor.py
```

如果本机有 Node：

```powershell
node --check static/app.js
node --check ..\killer_mortal_gui\index.js
node --check ..\killer_mortal_gui\boot.js
```

## 许可证

MortalCoach 本体采用 MIT License，详见 [LICENSE](LICENSE)。

第三方项目仍保留其原始许可证说明；其中 `killer_mortal_gui` 的 MIT License 保留在 `killer_mortal_gui/LICENSE`。
