"""Render the user's initial UI from Git without touching their data files."""
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

app = QApplication([])
for name in ("msyh.ttc", "segoeui.ttf"):
    QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
output = ROOT / "build" / "qa" / "original"
output.mkdir(parents=True, exist_ok=True)
source = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", "show", "106ebb2:ui.py"], cwd=ROOT).decode("utf-8")
with tempfile.TemporaryDirectory(dir=output) as directory:
    os.chdir(directory)
    Path("options.ini").write_text("FIXED_POSITION = False\nUSE_DARK_MODE = False\nFIXED_POSITION_X = 0\nFIXED_POSITION_Y = 0\n", encoding="utf-8")
    Path("todos.ini").write_text("<TODO-START-MARK>读完正在看的书\n记下三个值得保留的想法<TODO-START-MARK>整理本周的工作记录<TODO-START-MARK>给家里的绿植浇水", encoding="utf-8")
    module = types.ModuleType("original_ui")
    exec(compile(source, "original_ui.py", "exec"), module.__dict__)
    window = module.TODOApplication()
    window.show()
    QTest.qWait(400)
    window.adjustSize()
    app.processEvents()
    window.grab().save(str(output / "light.png"))
    module.load_colors(True)
    QTest.qWait(200)
    window.grab().save(str(output / "dark.png"))
    window.header_panel.settings_button.setChecked(True)
    QTest.qWait(400)
    window.grab().save(str(output / "settings.png"))
    # Qt destruction does not call the original close handler or persist data.
    window.hide()
    app.quit()
    os.chdir(ROOT)
os.chdir(ROOT)
print(f"Original UI reference: {output}")
