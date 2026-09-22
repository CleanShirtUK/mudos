#!/usr/bin/env python3
"""Small real GTK child used to validate delegated installer surfaces."""

import argparse
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-success", type=float, default=0.0)
    args = parser.parse_args()
    result = {"value": 2}
    window = Gtk.Window(title="Mudos synthetic installer")
    window.set_default_size(520, 220)
    window.connect("destroy", Gtk.main_quit)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_top(24); box.set_margin_bottom(24)
    box.set_margin_start(24); box.set_margin_end(24)
    box.pack_start(Gtk.Label(label="Synthetic interactive installer"), False, False, 0)
    controls = Gtk.Box(spacing=12)
    complete = Gtk.Button(label="Complete installation")
    cancel = Gtk.Button(label="Cancel installation")
    controls.pack_start(complete, True, True, 0)
    controls.pack_start(cancel, True, True, 0)
    box.pack_start(controls, False, False, 0)
    window.add(box)

    def finish(value: int) -> None:
        result["value"] = value
        Gtk.main_quit()

    complete.connect("clicked", lambda *_: finish(0))
    cancel.connect("clicked", lambda *_: finish(2))
    window.show_all()
    if args.auto_success > 0:
        GLib.timeout_add(int(args.auto_success * 1000), lambda: (finish(0), False)[1])
    Gtk.main()
    return int(result["value"])


if __name__ == "__main__":
    raise SystemExit(main())
