"""Prevent duplicate Agent processes and let a second launch focus the first."""

from __future__ import annotations

import ctypes
import hashlib
import os
import time

from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from agent_device import get_agent_data_dir


ERROR_ALREADY_EXISTS = 183


class AgentInstanceGuard:
    """Own a per-installation mutex and a small local activation endpoint."""

    def __init__(self, parent=None):
        identity = os.path.normcase(str(get_agent_data_dir())).casefold().encode("utf-8")
        suffix = hashlib.sha256(identity).hexdigest()[:24]
        self.server_name = f"SmartLabAgent-{suffix}"
        self.mutex_name = f"Local\\SmartLabAgent-{suffix}"
        self.server = QLocalServer(parent)
        self._kernel32 = None
        self._mutex_handle = None
        self._activate_callback = None

    def claim(self) -> bool:
        """Return False when another process already owns this installation."""
        if os.name == "nt":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = (
                ctypes.c_void_p,
                ctypes.c_bool,
                ctypes.c_wchar_p,
            )
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel32.CloseHandle.restype = ctypes.c_bool

            ctypes.set_last_error(0)
            handle = kernel32.CreateMutexW(None, False, self.mutex_name)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(handle)
                return False

            self._kernel32 = kernel32
            self._mutex_handle = handle

        if not self._listen():
            # Keep the mutex even if activation IPC is unavailable. That still
            # prevents duplicate monitoring processes from being started.
            print("Agent activation endpoint is unavailable; single-instance lock remains active.")
        return True

    def _listen(self) -> bool:
        self.server.newConnection.connect(self._accept_connections)
        if self.server.listen(self.server_name):
            return True

        # The mutex guarantees no current Agent owns this endpoint on Windows.
        # Removing it clears the stale local socket left by a terminated process.
        if QLocalServer.removeServer(self.server_name):
            return self.server.listen(self.server_name)
        return False

    def activate_existing(self, retries: int = 12) -> bool:
        """Signal the current Agent to reveal its login or session window."""
        for _ in range(max(1, retries)):
            socket = QLocalSocket()
            socket.connectToServer(self.server_name)
            if socket.waitForConnected(150):
                socket.write(b"activate\n")
                socket.waitForBytesWritten(150)
                socket.disconnectFromServer()
                return True
            time.sleep(0.1)

        # A mutex owner may still be finishing startup. Do not launch a second
        # copy just because its activation endpoint is not ready yet.
        return True

    def set_activation_callback(self, callback) -> None:
        self._activate_callback = callback

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            if client is None:
                continue

            def handle_request(connection=client):
                message = bytes(connection.readAll()).decode("utf-8", errors="ignore")
                if "activate" in message.splitlines() and self._activate_callback:
                    self._activate_callback()
                connection.disconnectFromServer()

            client.readyRead.connect(handle_request)
            client.disconnected.connect(client.deleteLater)
            if client.bytesAvailable():
                handle_request()

    def close(self) -> None:
        if self.server.isListening():
            self.server.close()
        QLocalServer.removeServer(self.server_name)
        if self._mutex_handle is not None and self._kernel32 is not None:
            self._kernel32.CloseHandle(self._mutex_handle)
            self._mutex_handle = None
