"""Application entrypoint; resources never depend on the working directory."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
from PyQt5.QtCore import QCoreApplication, QStandardPaths, Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication, QMessageBox
from platform_services import InstanceGuard
from settings_service import SettingsService
from task_store import TaskStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="My-TODOs-X 桌面待办")
    parser.add_argument("--autostart", action="store_true", help="按登录自启偏好启动")
    parser.add_argument("--data-dir", type=Path, help="指定独立数据目录，用于便携运行或测试")
    args = parser.parse_args(argv)
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0]])
    app.setApplicationName("My-TODOs-X")
    app.setOrganizationName("")
    app.setQuitOnLastWindowClosed(False)
    data_dir = args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    guard = store = log = None
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        log = logging.getLogger("mytodos")
        log.setLevel(logging.INFO)
        handler = RotatingFileHandler(data_dir / "mytodos.log", maxBytes=1024*1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        def unexpected_exception(kind, error, traceback):
            log.error("Unhandled Qt callback exception", exc_info=(kind, error, traceback))
            QMessageBox.critical(None, "My-TODOs-X 遇到错误", f"{error}\n\n未保存的输入会保留，详情已写入数据目录的 mytodos.log。")
        sys.excepthook = unexpected_exception
        guard = InstanceGuard(data_dir, app)
        if not guard.acquire(): return 0
        store = TaskStore(data_dir / "mytodos.sqlite3")
        legacy_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        store.migrate_legacy(legacy_dir)
        settings = SettingsService(store, app)
        from ui import TODOApplication
        window = TODOApplication(store, settings)
        log.info("Application ready; data=%s", data_dir)
        guard.activated.connect(window.restore_window)
        if not (args.autostart and settings.get("autostart_hidden") and window.tray_available):
            window.show()
        result = app.exec_()
        window.stop_services()
        return result
    except Exception as exc:
        if log: log.exception("Application startup failed")
        QMessageBox.critical(None, "My-TODOs-X 无法启动", f"{exc}\n\n数据文件会保留，请检查权限或从备份恢复。")
        return 1
    finally:
        if store: store.close()
        if guard: guard.close()


if __name__ == "__main__":
    sys.exit(main())
