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

## 3. 新机器流程验证

在一个没有 `node_modules/`、没有 `data/` 的目录中测试：

```powershell
.\Start-MortalCoach.bat
```

预期：

- 自动安装 Electron
- 自动创建 `mortalcoach/data/`
- 打开 MortalCoach 桌面窗口
- `doctor` 显示项目文件完整

## 4. 基础功能烟测

- 切换深色 / 浅色主题
- 打开牌谱库
- 删除一份测试牌谱
- 重命名一份测试牌谱
- 打开复盘页
- 在棋盘中点击上一错误 / 下一错误，右侧栏同步变化
- 切换训练档案的雀魂 / 天凤 tab，天凤下不显示雀魂趋势

## 5. 文档检查

- 根 README 能解释项目用途和快速开始
- `mortalcoach/README.md` 能解释本体运行方式
- 第三方 KillerDucky License 保留
- 没有本机绝对路径
- 没有个人账号、token、cookie、SQLite 数据库

## 6. 许可证

发布前需要决定 MortalCoach 本体许可证。

建议候选：

- MIT：最宽松，适合个人开源工具
- Apache-2.0：更正式，包含专利授权条款
- 不选择许可证：别人只能查看代码，不能明确复用

`killer_mortal_gui/` 自身为 MIT License，需要保留其 LICENSE。
