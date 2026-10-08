"""Validated settings shared by the settings panel, tray and startup."""
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

DEFAULTS = {
    "dark_mode": False, "position_locked": False, "always_on_top": False,
    "window_opacity": 1.0, "window_width": 500, "window_height": 640,
    "window_x": None, "window_y": None, "close_behavior": "ask",
    "autostart": False, "autostart_hidden": False,
}


class SettingsService(QObject):
    changed = pyqtSignal(str, object)
    error = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        saved = store.settings()
        self.values = {key: self.normalize(key, saved.get(key, default)) for key, default in DEFAULTS.items()}
        self.pending = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.flush)

    @staticmethod
    def normalize(key, value):
        default = DEFAULTS[key]
        if isinstance(default, bool):
            return value if isinstance(value, bool) else default
        if key == "close_behavior":
            return value if value in ("ask", "tray", "quit") else default
        if key == "window_opacity":
            return max(.3, min(1., float(value))) if isinstance(value, (int, float)) else default
        if key in ("window_x", "window_y"):
            return value if isinstance(value, int) and not isinstance(value, bool) else None
        if key in ("window_width", "window_height"):
            minimum = 380 if key == "window_width" else 320
            return max(minimum, min(10000, value)) if isinstance(value, int) else default
        return value

    def get(self, key):
        return self.values[key]

    def set(self, key, value, deferred=False):
        return self.set_many({key: value}, deferred)

    def set_many(self, values, deferred=False):
        values = {k: self.normalize(k, v) for k, v in values.items()}
        values = {k: v for k, v in values.items() if self.values[k] != v}
        if not values:
            return True
        if not deferred:
            try:
                self.store.save_settings(values)
            except Exception as exc:
                self.error.emit(f"设置未保存：{exc}")
                return False
        self.values.update(values)
        if deferred:
            self.pending.update(values)
            self.timer.start()
        else:
            for key in values:
                self.pending.pop(key, None)
        for key, value in values.items():
            self.changed.emit(key, value)
        return True

    def flush(self):
        self.timer.stop()
        if not self.pending:
            return True
        try:
            self.store.save_settings(self.pending)
            self.pending.clear()
            return True
        except Exception as exc:
            self.error.emit(f"设置未保存：{exc}")
            return False
