"""Event-driven observation of the Gamescope focused Xwayland surface."""

from __future__ import annotations

import asyncio
import logging
import select
import threading
from typing import Callable

from Xlib import X, display


WindowStateCallback = Callable[[int | None, int | None, bool], None]


class GamescopeWindowObserver:
    """Report Gamescope focus and effective fullscreen geometry without polling."""

    def __init__(self, loop: asyncio.AbstractEventLoop, callback: WindowStateCallback,
                 display_name: str | None = None) -> None:
        self._loop = loop
        self._callback = callback
        self._display_name = display_name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log = logging.getLogger("lulu.gamescope_observer")

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="gamescope-window-observer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._observe_once()
            self._stop.wait(1.0)

    def _observe_once(self) -> None:
        connection = None
        try:
            connection = display.Display(self._display_name)
            root = connection.screen().root
            focus_atom = connection.intern_atom("GAMESCOPE_FOCUSED_WINDOW")
            focusable_atom = connection.intern_atom("GAMESCOPE_FOCUSABLE_WINDOWS")
            fullscreen_atom = connection.intern_atom("_NET_WM_STATE_FULLSCREEN")
            state_atom = connection.intern_atom("_NET_WM_STATE")
            root.change_attributes(event_mask=X.PropertyChangeMask)
            watched_xid: int | None = None
            focused = fullscreen = False
            last_emitted: tuple[int | None, int | None, bool] | None = None
            width, height = connection.screen().width_in_pixels, connection.screen().height_in_pixels

            def emit(xid: int | None, pid: int | None, is_focused: bool, is_fullscreen: bool) -> None:
                nonlocal last_emitted
                state = (xid, pid, is_focused and is_fullscreen)
                if state == last_emitted:
                    return
                last_emitted = state
                self._loop.call_soon_threadsafe(self._callback, *state)

            def refresh(xid: int | None) -> None:
                nonlocal watched_xid, focused, fullscreen
                if watched_xid is not None and watched_xid != xid:
                    try:
                        connection.create_resource_object("window", watched_xid).change_attributes(
                            event_mask=X.NoEventMask)
                    except Exception:
                        pass
                watched_xid = xid
                focused = xid is not None
                if xid is None:
                    fullscreen = False
                    emit(None, None, False, False)
                    return
                window = connection.create_resource_object("window", xid)
                try:
                    window.change_attributes(event_mask=X.PropertyChangeMask | X.StructureNotifyMask)
                    candidates = root.get_full_property(focusable_atom, X.AnyPropertyType)
                    pid = None
                    if candidates is not None:
                        values = list(candidates.value)
                        pid = next((int(values[index + 2]) for index in range(0, len(values) - 2, 3)
                                    if int(values[index]) == xid), None)
                    if pid is None:
                        pid_prop = window.get_full_property(connection.intern_atom("_NET_WM_PID"), X.AnyPropertyType)
                        pid = int(pid_prop.value[0]) if pid_prop is not None and len(pid_prop.value) else None
                    state = window.get_full_property(state_atom, X.AnyPropertyType)
                    has_fullscreen_state = state is not None and fullscreen_atom in state.value
                    geometry = window.get_geometry()
                    translated = root.translate_coords(window, 0, 0)
                    fullscreen = has_fullscreen_state or (
                        translated.x <= 0 and translated.y <= 0
                        and geometry.width >= width and geometry.height >= height
                    )
                    emit(xid, pid, focused, fullscreen)
                except Exception:
                    emit(xid, None, focused, False)

            initial = root.get_full_property(focus_atom, X.AnyPropertyType)
            refresh(int(initial.value[0]) if initial is not None and len(initial.value) else None)

            while not self._stop.is_set():
                select.select([connection.fileno()], [], [], 0.5)
                while connection.pending_events():
                    event = connection.next_event()
                    if event.type == X.PropertyNotify and event.window.id == root.id \
                            and event.atom in (focus_atom, focusable_atom):
                        if event.atom == focus_atom:
                            prop = root.get_full_property(focus_atom, X.AnyPropertyType)
                            xid = int(prop.value[0]) if prop is not None and len(prop.value) else 0
                            refresh(xid or None)
                        else:
                            refresh(watched_xid)
                    elif watched_xid is not None and event.window.id == watched_xid:
                        refresh(watched_xid)
                connection.flush()
        except Exception:
            self._log.exception("Gamescope window observer stopped")
            self._loop.call_soon_threadsafe(self._callback, None, None, False)
        finally:
            if connection is not None:
                connection.close()
