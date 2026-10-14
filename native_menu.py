#!/usr/bin/env python3
"""Persistent Night Light settings using the installed SpruceOS PyUI views.

Run with Spruce's MainUI runtime, just like its mainui.py entrypoint. Only
this process is customized; no installed SpruceOS files are changed.
"""
import sys
import time
import traceback
from pathlib import Path

from nightlight_core import load_settings, discover_crtc, apply

APP = Path('/mnt/SDCARD/App/NightLight')
MAIN_PY = Path('/mnt/SDCARD/App/PyUI/main-ui/mainui.py')


def value_menu(settings, key):
    rows = {}
    for amount in range(0, 101, 5):
        filled = amount // 10
        bar = '[' + '=' * filled + '-' * (10 - filled) + ']'
        mark = '* ' if amount == settings[key] else '  '
        rows['{}{:3d}% {}'.format(mark, amount, bar)] = str(amount)
    return rows


def edit_settings(settings):
    # Import after mainui has configured the device, theme and display.
    from controller.controller_inputs import ControllerInput
    from option_select_ui import OptionSelectUI
    from views.grid_or_list_entry import GridOrListEntry
    from views.view_creator import ViewCreator
    from views.view_type import ViewType

    selected_index = 0
    view = None
    while True:
        rows = [
            ('Warm light: ' + ('ON' if settings['enabled'] else 'OFF'),
             'TOGGLE', 'Press A to toggle the filter'),
            ('Intensity: {}%'.format(settings['intensity']),
             'intensity', 'Select the desired warmth level'),
            ('Orange tone: {}%'.format(settings['amber']),
             'amber', 'Select how amber the colour becomes'),
            ('APPLY & RETURN', 'APPLY', 'Save and apply your chosen settings'),
            ('CANCEL', 'CANCEL', 'Leave without changes'),
        ]
        options = [GridOrListEntry(primary_text=label, value=token,
                                   image_path=str(APP / 'sunset.png'),
                                   description=description)
                   for label, token, description in rows]
        # PyUI returns after each input cycle, including navigation and idle
        # frames. Keep its view alive so its highlight/scroll state survives.
        # This matches BasicSettingsMenu.show_menu in SpruceOS.
        if view is None:
            view = ViewCreator.create_view(
                view_type=ViewType.TEXT_AND_IMAGE,
                top_bar_text='NIGHT LIGHT', options=options,
                selected_index=selected_index)
        else:
            view.set_options(options)
        selected = view.get_selection([ControllerInput.A, ControllerInput.B])
        if selected is None:
            continue
        if selected.get_input() == ControllerInput.B:
            return False
        if selected.get_input() != ControllerInput.A:
            continue
        selected_index = selected.get_index()
        choice = selected.get_selection().get_value()
        if choice == 'TOGGLE':
            settings['enabled'] = not settings['enabled']
        elif choice in ('intensity', 'amber'):
            value = OptionSelectUI.navigate_menu(
                menu_dict=value_menu(settings, choice),
                title=rows[selected_index][0], folder=str(APP),
                exit_after_running=False, view_type=ViewType.TEXT_AND_IMAGE,
                is_root=False)
            if value is not None:
                settings[choice] = int(value)
        elif choice == 'APPLY':
            return True
        elif choice == 'CANCEL':
            return False


def main():
    if not MAIN_PY.is_file():
        raise RuntimeError('Cannot locate the SpruceOS PyUI entrypoint')
    started = time.monotonic()
    settings = load_settings()
    # Capture the active framebuffer before SDL starts. Its IDs remain valid
    # after SDL closes, even if shutdown temporarily leaves no active FB.
    crtc = discover_crtc()
    print('Active CRTC: %r (%.2fs)' % (crtc, time.monotonic() - started), flush=True)
    sys.path.insert(0, str(MAIN_PY.parent))
    import mainui
    from display.display import Display

    def show_nightlight(args):
        print('Night Light menu ready (%.2fs)' % (time.monotonic() - started), flush=True)
        try:
            should_apply = edit_settings(settings)
        finally:
            # Release DRM master once, when leaving the menu, never on edits.
            Display.deinit_display()
        if should_apply:
            apply(settings, crtc)
            print('SUCCESS: new Night Light settings applied', flush=True)
        else:
            print('Cancelled; original saved settings unchanged', flush=True)
        # Do not fall through into Spruce's full main menu/startup tasks.
        raise SystemExit(0)

    # Reuse Spruce's installed initialization and native views in this process.
    # The option-list flag selects auxiliary mode; our hook owns the menu and
    # does not read an option-list file or execute shell commands for selections.
    mainui.check_for_option_list_file = show_nightlight
    mainui.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAILED: %s' % exc, flush=True)
        traceback.print_exc()
        sys.exit(1)
