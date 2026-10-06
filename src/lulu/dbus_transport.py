"""D-Bus transport helpers for services using dbus-next's asyncio bus."""

from __future__ import annotations

from dbus_next.aio import MessageBus
from dbus_next.aio.message_bus import (
    _MessageWriter, _future_set_exception, _future_set_result,
)


class BackpressureSafeMessageWriter(_MessageWriter):
    """Treat EAGAIN on the nonblocking D-Bus socket as normal backpressure.

    dbus-next's default writer treats BlockingIOError as fatal. A writable
    callback can race with socket-buffer pressure, so preserve the pending
    message and let the event loop invoke the writer again when writable.
    """

    def write_callback(self) -> None:
        try:
            while True:
                if self.buf is None:
                    if self.messages.qsize() == 0:
                        self.loop.remove_writer(self.fd)
                        return
                    buf, unix_fds, future = self.messages.get_nowait()
                    self.unix_fds = unix_fds
                    self.buf = memoryview(buf)
                    self.offset = 0
                    self.fut = future

                try:
                    if self.unix_fds and self.negotiate_unix_fd:
                        import array
                        import socket

                        ancdata = [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                    array.array("i", self.unix_fds))]
                        self.offset += self.sock.sendmsg([self.buf[self.offset:]], ancdata)
                        self.unix_fds = None
                    else:
                        self.offset += self.sock.send(self.buf[self.offset:])
                except BlockingIOError:
                    return

                if self.offset >= len(self.buf):
                    self.buf = None
                    _future_set_result(self.fut, None)
                else:
                    return
        except Exception as error:
            _future_set_exception(self.fut, error)
            self.bus._finalize(error)


class BackpressureSafeMessageBus(MessageBus):
    """MessageBus whose writer survives transient nonblocking-socket EAGAIN."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._writer = BackpressureSafeMessageWriter(self)
