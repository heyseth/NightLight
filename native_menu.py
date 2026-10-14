#!/usr/bin/env python3
"""Persistent Night Light settings using the installed SpruceOS PyUI views.

Run with Spruce's MainUI runtime, just like its mainui.py entrypoint. Only
this process is customized; no installed SpruceOS files are changed.
"""
import sys
import os
import time
import traceback
import importlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nightlight_core import load_settings, discover_crtc, apply

MAIN_PY = Path('/mnt/SDCARD/App/PyUI/main-ui/mainui.py')


def load_runtime():
    """Overlap the read-only display query with PyUI's module imports.

    Both must finish before mainui.main() can initialize SDL/DRM. Do not
    cache CRTC IDs between launches: they belong to the running kernel.
    """
    def query_display():
        started = time.monotonic()
        crtc = discover_crtc()
        print('Display discovery: %.2fs; active CRTC: %r' %
              (time.monotonic() - started, crtc), flush=True)
        return crtc

    with ThreadPoolExecutor(max_workers=1) as worker:
        discovery = worker.submit(query_display)
        started = time.monotonic()
        runtime = importlib.import_module('mainui')
        print('PyUI imports: %.2fs' % (time.monotonic() - started), flush=True)
        return runtime, discovery.result()


def edit_settings(settings):
    # Import after mainui has configured the device, theme and display.
    from controller.controller_inputs import ControllerInput
    from views.grid_or_list_entry import GridOrListEntry
    from views.view_creator import ViewCreator
    from views.view_type import ViewType

    selected_index = 0
    view = None
    while True:
        rows = [
            ('Warm light', 'TOGGLE', '<    {}    >'.format('ON' if settings['enabled'] else 'OFF')),
            ('Intensity', 'intensity', '<    {}%    >'.format(settings['intensity'])),
            ('Orange tone', 'amber', '<    {}%    >'.format(settings['amber'])),
            ('Apply & Exit', 'APPLY', None),
            ('Discard & Exit', 'CANCEL', None),
        ]
        options = [GridOrListEntry(primary_text=label, value=token,
                                   value_text=value_text)
                   for label, token, value_text in rows]
        # PyUI returns after each input cycle, including navigation and idle
        # frames. Keep its view alive so its highlight/scroll state survives.
        # This matches BasicSettingsMenu.show_menu in SpruceOS.
        if view is None:
            view = ViewCreator.create_view(
                # Spruce's settings renderer uses the full screen width,
                # with static labels and a separate right-aligned value.
                view_type=ViewType.ICON_AND_DESC,
                top_bar_text='Night Light', options=options,
                selected_index=selected_index)
        else:
            view.set_options(options)
        selected = view.get_selection([ControllerInput.A, ControllerInput.B,
                                       ControllerInput.DPAD_LEFT, ControllerInput.DPAD_RIGHT])
        if selected is None:
            continue
        button = selected.get_input()
        if button == ControllerInput.B:
            return False
        if button not in (ControllerInput.A, ControllerInput.DPAD_LEFT, ControllerInput.DPAD_RIGHT):
            continue
        selected_index = selected.get_index()
        choice = selected.get_selection().get_value()
        if choice == 'TOGGLE':
            settings['enabled'] = not settings['enabled']
        elif choice in ('intensity', 'amber'):
            if button in (ControllerInput.DPAD_LEFT, ControllerInput.DPAD_RIGHT):
                step = -5 if button == ControllerInput.DPAD_LEFT else 5
                settings[choice] = max(0, min(100, settings[choice] + step))
        elif choice == 'APPLY' and button == ControllerInput.A:
            return True
        elif choice == 'CANCEL' and button == ControllerInput.A:
            return False


def main():
    if not MAIN_PY.is_file():
        raise RuntimeError('Cannot locate the SpruceOS PyUI entrypoint')
    started = time.monotonic()
    settings = load_settings()
    # Capture the active framebuffer before SDL starts. Its IDs remain valid
    # after SDL closes, even if shutdown temporarily leaves no active FB.
    sys.path.insert(0, str(MAIN_PY.parent))
    mainui, crtc = load_runtime()
    initialized = time.monotonic()
    import sdl2

    def show_nightlight(args):
        print('PyUI initialization: %.2fs; menu ready: %.2fs' %
              (time.monotonic() - initialized, time.monotonic() - started), flush=True)
        try:
            should_apply = edit_settings(settings)
        finally:
            exiting = time.monotonic()
            # This process never renders again. SDL_Quit releases the window,
            # renderer and DRM master without PyUI's reusable-display cleanup
            # (which can include a global disk sync, GC and an extra sleep).
            # Remaining Python/font allocations are reclaimed on process exit.
            sdl2.SDL_Quit()
            print('SDL shutdown: %.2fs' % (time.monotonic() - exiting), flush=True)
        if should_apply:
            apply(settings, crtc)
            print('SUCCESS: new Night Light settings applied', flush=True)
        else:
            print('Cancelled; original saved settings unchanged', flush=True)
        print('Exit work complete: %.2fs' % (time.monotonic() - exiting), flush=True)
        # Do not fall through into Spruce's full main menu/startup tasks.
        raise SystemExit(0)

    # Reuse Spruce's installed initialization and native views in this process.
    # The option-list flag selects auxiliary mode; our hook owns the menu and
    # does not read an option-list file or execute shell commands for selections.
    mainui.check_for_option_list_file = show_nightlight
    mainui.main()


def run():
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise
    except Exception as exc:
        print('FAILED: %s' % exc, flush=True)
        traceback.print_exc()
        sys.exit(1)
    # All display/DRM work and settings writes have finished. Match Spruce's
    # final process exit instead of waiting for imported UI worker threads or
    # running destructors against the now-closed SDL display.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == '__main__':
    run()
