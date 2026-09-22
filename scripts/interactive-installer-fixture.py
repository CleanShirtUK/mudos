#!/usr/bin/env python3
"""Small real GTK child used to validate delegated installer surfaces."""

import argparse
import subprocess
import sys
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-success", type=float, default=0.0)
    parser.add_argument("--replacement-child", action="store_true")
    parser.add_argument("--replace-after", type=float, default=1.0)
    parser.add_argument("--replacement-auto-success", type=float, default=0.0)
    args = parser.parse_args()
    result = {"value": 2}
    window = Gtk.Window(title="Mudos synthetic replacement" if args.replacement_child else "Mudos synthetic installer")
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
    if not args.replacement_child:
        replacement = subprocess.Popen([sys.executable, __file__, "--replacement-child",
                                        "--auto-success", str(args.replacement_auto_success)],
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        def handoff() -> bool:
            # Bootstrapper completion is successful; the owned replacement
            # remains the transaction's interactive child.
            result["value"] = 0
            window.destroy()
            Gtk.main_quit()
            return False
        GLib.timeout_add(int(args.replace_after * 1000), handoff)
    else:
        replacement = None
    if args.auto_success > 0:
        GLib.timeout_add(int(args.auto_success * 1000), lambda: (finish(0), False)[1])
    Gtk.main()
    if replacement is not None:
        # The replacement is intentionally left to the supervisor's owned
        # process-group lifecycle; do not wait for it here.
        pass
    return int(result["value"])


if __name__ == "__main__":
    raise SystemExit(main())
