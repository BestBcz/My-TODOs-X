import os
import sys
from pathlib import Path
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

@pytest.fixture(scope="session", autouse=True)
def headless_fonts(qapp):
    # Qt's Windows offscreen plugin has no system font database of its own.
    if sys.platform == "win32":
        from PyQt5.QtGui import QFontDatabase
        for name in ("msyh.ttc", "segoeui.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
