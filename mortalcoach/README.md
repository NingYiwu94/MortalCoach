# MortalCoach App

这里是 MortalCoach 的应用本体。普通用户不需要直接进入这个目录启动。

普通玩家请优先下载 GitHub Release 里的安装包，不需要进入这个目录。

如果你在调试源码版，请从仓库根目录运行：

```powershell
.\Start-MortalCoach.bat
```

如果你要生成 Windows 安装包，请从仓库根目录运行：

```powershell
.\Package-MortalCoach.bat
```

环境检查：

```powershell
.\Start-MortalCoach.bat doctor
```

## 开发者说明

如果需要调试桌面端：

```powershell
npm install
npm run desktop
```

如果需要检查 Python 文件：

```powershell
python -m py_compile app.py db.py scripts/doctor.py
```

## 数据位置

源码版本地数据保存在：

```text
mortalcoach/data/
```

安装包版本地数据保存在：

```text
%APPDATA%\MortalCoach\data\
```

主要包括：

- `mortalcoach.sqlite3`：牌谱库、复盘记录、训练档案
- `electron-profile/`：Electron 内嵌网页的本地配置和缓存
- `backups/`：隐藏维护接口生成的备份

这些都是个人数据，已经在 `.gitignore` 中排除。

## 文件结构

```text
mortalcoach/
  app.py                 本地 HTTP 服务和 API
  db.py                  SQLite 数据层
  analysis.py            结构化复盘 JSON 解析
  link_utils.py          输入链接/JSON/HTML 判定
  desktop/               Electron 主进程
  scripts/               环境检查和旧流程辅助脚本
  static/                MortalCoach 前端
  samples/               示例复盘 JSON
```
