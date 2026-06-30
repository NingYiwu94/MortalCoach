# Release Checklist

发布到 GitHub 前建议按顺序检查：

## 1. 清理本地数据

确认以下内容没有出现在 `git status` 中：

- `mortalcoach/data/`
- `mortalcoach/config.json`
- `mortalcoach/node_modules/`
- `__pycache__/`
- `.env`
- 上游源码临时副本，例如 `Mortal/`、`mjai-reviewer-master/`

## 2. 环境检查

```powershell
.\Start-MortalCoach.bat doctor
cd mortalcoach
python -m py_compile app.py db.py scripts/doctor.py
```

如果本机有 Node：

```powershell
node --check static/app.js
node --check ..\killer_mortal_gui\index.js
node --check ..\killer_mortal_gui\boot.js
```

## 3. 生成安装包

在仓库根目录运行：

```powershell
.\Package-MortalCoach.bat
```

预期：

- 生成 `release/MortalCoach-Setup-*.exe`
- 生成 `release/win-unpacked/`
- 打包后的后端在 `release/win-unpacked/resources/backend/MortalCoachBackend.exe`
- 安装包不应提交进 git，只上传到 GitHub Release

## 4. 安装包流程验证

在一台尽量干净的 Windows 10 / 11 上测试 `release/MortalCoach-Setup-*.exe`：

- 不预装 Python 也能打开 MortalCoach
- 不预装 Node.js 也能打开 MortalCoach
- 安装器创建桌面快捷方式
- 桌面快捷方式能打开 MortalCoach
- 首次运行会在 `%APPDATA%\MortalCoach\data\` 创建个人数据
- 粘贴牌谱链接后能打开内嵌官方 Mortal 分析窗口

## 5. 基础功能烟测

- 切换深色 / 浅色主题
- 打开牌谱库
- 删除一份测试牌谱
- 重命名一份测试牌谱
- 打开复盘页
- 在棋盘中点击上一错误 / 下一错误，右侧栏同步变化
- 切换训练档案的雀魂 / 天凤 tab，天凤下不显示雀魂趋势

## 6. 文档检查

- 根 README 能解释项目用途和快速开始
- `mortalcoach/README.md` 能解释本体运行方式
- 第三方 KillerDucky License 保留
- 没有本机绝对路径
- 没有个人账号、token、cookie、SQLite 数据库

## 7. GitHub Release

- 上传 `release/MortalCoach-Setup-*.exe`
- 上传 `release/MortalCoach-Setup-*.exe.blockmap` 和 `release/latest.yml`，这两个文件是 electron-updater 自动更新必需的元数据
- Release 标题使用版本号，例如 `MortalCoach v0.1.0`
- Release 说明包含：
  - 推荐 Windows 10 / 11
  - 下载并双击安装包
  - 首次运行可能需要等待官方 Mortal 页面加载
  - 数据保存在 `%APPDATA%\MortalCoach\data\`

## 8. 许可证

MortalCoach 本体采用 MIT License，根目录需要保留 `LICENSE`。

`killer_mortal_gui/` 自身为 MIT License，需要保留其 LICENSE。
