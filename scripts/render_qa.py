"""Render QA screenshots in an isolated profile; no desktop input injection."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication
from task_store import TaskStore
from ui import TODOApplication

def main():
    scale = os.environ.get("QT_SCALE_FACTOR", "1")
    app = QApplication([])
    if sys.platform == "win32":
        for name in ("msyh.ttc", "segoeui.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
    output = ROOT / "build" / "qa"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        store = TaskStore(Path(directory) / "qa.sqlite3")
        store.save_settings({"close_behavior": "quit", "autostart": False})
        category = store.add_category("工作")
        now = datetime.now(timezone.utc)
        store.add("完善 My-TODOs-X 的窗口适配", pinned=True, category_id=category, priority=2)
        store.add("整理本周的工作记录，导出一份 Markdown 周报", category_id=category,
                  due_at=now+timedelta(days=1), remind_at=now+timedelta(hours=1))
        store.add("读完正在看的书\n记下三个值得保留的想法")
        store.add("给家里的绿植浇水", priority=0)
        done = store.add("备份旧版待办数据")
        store.complete(done.id)
        window = TODOApplication(store, tray_available=False, exit_app=False)
        window.show()
        app.processEvents()
        window.grab().save(str(output / f"light-{scale}.png"))
        window.resize(380, 500)
        window.settings.set("dark_mode", True)
        app.processEvents()
        window.grab().save(str(output / f"dark-narrow-{scale}.png"))
        window.new_task()
        window.editor.text.setPlainText("试试新的编辑面板\n支持多行内容、分类和独立提醒")
        app.processEvents()
        window.grab().save(str(output / f"editor-{scale}.png"))
        window.editor.baseline = None
        window.open_settings()
        app.processEvents()
        window.grab().save(str(output / f"settings-{scale}.png"))
        window.show_list()
        for n in range(500): store.add(f"性能测试事项 {n}：文字随窗口宽度自然换行。"*2)
        window.refresh()
        times = []
        for width in range(380, 901, 20):
            begin = perf_counter()
            window.resize(width, 640)
            app.processEvents()
            times.append((perf_counter()-begin)*1000)
        times.sort()
        print(json.dumps({"scale": scale, "rows": window.model.rowCount(),
                          "resize_p95_ms": round(times[int(len(times)*.95)], 2),
                          "resize_max_ms": round(max(times), 2)}))
        window.close()
        store.close()

if __name__ == "__main__": main()
