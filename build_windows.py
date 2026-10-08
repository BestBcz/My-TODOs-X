"""Reproducible onedir Windows build and ZIP, run using the project venv."""
import os
import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main():
    if sys.platform != "win32":
        raise SystemExit("请在 Windows x64 上构建 Windows 程序。")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from widgets import icon
    app = QApplication([])
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    ico = build / "app.ico"
    if not icon("calendar").pixmap(256, 256).save(str(ico), "ICO"):
        raise RuntimeError("无法生成应用图标")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
                    "--name", "My-TODOs-X", "--icon", str(ico),
                    "--add-data", f"{ROOT / 'LICENSE'};.",
                    "--add-data", f"{ROOT / 'NOTICE.md'};.",
                    "--add-data", f"{ROOT / 'icons' / 'icons.dat'};icons",
                    str(ROOT / "start.py")], cwd=ROOT, check=True)
    destination = ROOT / "dist" / "My-TODOs-X"
    for name in ("README.md", "LICENSE", "NOTICE.md"):
        shutil.copy2(ROOT / name, destination / name)
    source = destination / "source"
    source.mkdir(exist_ok=True)
    for file in ROOT.iterdir():
        if file.is_file() and (file.suffix == ".py" or file.name.startswith("requirements") or file.name in ("README.md", "LICENSE", "NOTICE.md", "pytest.ini")):
            shutil.copy2(file, source / file.name)
    for name in ("siui", "components", "icons", "assets", "scripts", "tests"):
        shutil.copytree(ROOT / name, source / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    licenses = destination / "third-party-licenses"
    licenses.mkdir(exist_ok=True)
    for package in ("PyQt5", "PyQt5-Qt5", "PyQt5-sip", "PyInstaller"):
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if "license" in str(file).lower() or Path(str(file)).name.lower().startswith("copying"):
                original = Path(distribution.locate_file(file))
                if original.is_file():
                    target = licenses / package / Path(str(file)).name
                    target.parent.mkdir(exist_ok=True)
                    shutil.copy2(original, target)
    pyqt_license = licenses / "PyQt5"
    pyqt_license.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "LICENSE", pyqt_license / "LICENSE-GPL-v3.txt")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists(): shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    archive = shutil.make_archive(str(ROOT / "dist" / "My-TODOs-X-Windows-x64"), "zip", ROOT / "dist", "My-TODOs-X")
    print(f"Windows 程序：{destination / 'My-TODOs-X.exe'}\nZIP：{archive}")

if __name__ == "__main__": main()
