# My-TODOs-X

基于 [ChinaIceF / 霏泠 Ice 的 My-TODOs](https://github.com/ChinaIceF/My-TODOs) 增强的本地桌面待办工具。保留简洁卡片、圆角及深浅主题，优先支持 Windows。

## 使用 Windows 程序

解压 `My-TODOs-X-Windows-x64.zip`，运行文件夹里的 `My-TODOs-X.exe`。请保留同目录的 `_internal` 文件夹。无需安装 Python。ZIP 同时包含 source 完整源码和第三方许可证。

- 鼠标拖动窗口四边或四角调整大小；拖动标题区域移动。内容会自动换行，长清单可以滚动。
- 标题栏 `+` 新建事项，双击事项修改，右键或悬停后的更多按钮操作事项。
- 勾选后进入“已完成”，取消勾选可恢复；删除进入回收站，永久删除需确认。
- 分类、高中低优先级、事项置顶、搜索及四种排序均可使用。完整未完成清单采用手动排序时可拖动事项调整顺序，置顶事项保持在最前。
- 设置中的“不透明度”范围为 30%～100%，背景、文字和按钮一起变化；“窗口始终在最前”与事项置顶分别控制。
- 首次关闭选择后台常驻或退出，可记住选择。托盘可恢复窗口、添加事项、切换窗口置顶和明确退出。
- 登录自启默认关闭；开启后默认显示窗口，也可选择只在托盘运行。移动程序目录后请关闭再重新开启自启以更新启动路径。
- 截止时间和一次提醒分别设置，提醒无需截止时间。完成或删除后停止提醒。程序退出时无法发通知，错过的提醒在下次启动或休眠恢复后合并补发；Windows 通知设置和勿扰模式会影响系统通知显示。
- “每周总结”按周一至周日汇总新增、完成、待办、逾期及分类，可查看历史周，复制或导出 Markdown。本周截至当前时刻，其他周截至该周结束。

快捷键：`Ctrl+N` 新建，`Ctrl+F` 搜索，`Ctrl+,` 设置，编辑面板 `Ctrl+Enter` 保存。列表选中事项后 `Enter` 修改、`Delete` 移入回收站。

## 数据与旧版迁移

默认数据库保存在 `%LOCALAPPDATA%\My-TODOs-X\mytodos.sqlite3`，设置页可查看实际路径。事项和历史记录即时保存，移动或更新程序不会改变数据位置；每个数据目录只允许一个运行实例，重复启动唤回已有窗口。

首次启动会自动迁移程序旁的旧 `todos.ini`、`options.ini`，原文件保持不变，备份保存在用户数据目录的 `legacy-backup`。也可在设置中手动导入旧 `todos.ini`。重复手动导入会新增一批事项。旧数据没有创建时间，因此不会算作导入当周新增。

已经发生的完成记录保留在周报事件中，后续编辑、恢复或删除事项不会改写已结束的周报。永久删除回收站事项不会清除历史周报记录。

备份时先退出程序，再复制整个用户数据目录。可通过 `--data-dir "D:\My Todo Data"` 指定独立数据目录，通过 `--autostart` 使用自启显示偏好。macOS/Linux 保留源码运行兼容，登录自启设置本轮限定 Windows。

## 源码运行、测试和打包

当前验证环境为 Windows x64、Python 3.14。运行依赖锁定在 `requirements.txt`，开发环境完整依赖锁定在 `requirements-lock.txt`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe start.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe build_windows.py
```

构建输出位于 `dist\My-TODOs-X\` 及 `dist\My-TODOs-X-Windows-x64.zip`。自动化测试使用临时数据库和隔离的 Qt 环境，不修改真实待办或 Windows 自启设置。`scripts/render_qa.py` 可生成隔离界面截图及 500 项清单缩放性能数据。

## 许可与致谢

按 [GNU GPL v3](LICENSE) 发布；原作者署名、[PyQt-SiliconUI](https://github.com/ChinaIceF/PyQt-SiliconUI) 和随附图标声明见 [NOTICE.md](NOTICE.md)。本项目的源代码与构建脚本位于 [My-TODOs-X 仓库](https://github.com/BestBcz/My-TODOs-X)。
