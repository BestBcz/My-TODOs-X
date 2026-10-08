from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class ReminderService(QObject):
    due = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.check)

    def start(self):
        self.timer.start()
        self.check()

    def check(self):
        try:
            tasks = self.store.pending_reminders()
            if tasks:
                self.store.mark_reminders_sent([t.id for t in tasks])
                self.due.emit(tasks)
        except Exception as exc:
            self.timer.stop()
            self.error.emit(f"提醒暂时停止，请检查数据文件：{exc}")

    def stop(self):
        self.timer.stop()
