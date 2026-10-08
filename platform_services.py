"""OS integration and single-instance activation, isolated for testing."""
import hashlib
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QObject, QLockFile, QThread, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "My-TODOs-X"


def launch_command(executable=None, frozen=None, source=None):
    executable = Path(executable or sys.executable).resolve()
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    args = [str(executable)]
    if not frozen:
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            args[0] = str(pythonw)
        args.append(str(Path(source or Path(__file__).with_name("start.py")).resolve()))
    return subprocess.list2cmdline([*args, "--autostart"])


def set_autostart(enabled):
    if sys.platform != "win32":
        raise RuntimeError("登录自启目前支持 Windows")
    import winreg
    command = launch_command()
    if enabled and len(command) > 260:
        raise ValueError("启动路径过长，请将程序移动到较短路径后启用自启")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def autostart_enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, RUN_NAME)[0])
    except OSError:
        return False


class InstanceGuard(QObject):
    activated = pyqtSignal()

    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        identity = str(Path(data_dir).resolve()).casefold().encode()
        self.name = "mytodos-x-" + hashlib.sha256(identity).hexdigest()[:24]
        self.lock = QLockFile(str(Path(data_dir) / "instance.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._activate)
        self.primary = False

    def acquire(self):
        if self.lock.tryLock(0):
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise RuntimeError("无法建立应用唤回通道")
            self.primary = True
            return True
        socket = QLocalSocket(self)
        # Give a simultaneous first launch time to initialize its listener.
        for _ in range(10):
            socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                socket.write(b"show")
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
                return False
            socket.abort()
            QThread.msleep(100)
        raise RuntimeError("已有实例正在启动或无法响应，请稍后重试。")

    def _activate(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
            connection.disconnectFromServer()
            self.activated.emit()

    def close(self):
        if self.primary:
            self.server.close()
            self.lock.unlock()
            self.primary = False
