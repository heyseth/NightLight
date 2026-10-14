#!/usr/bin/env python3
"""Night Light UI using SpruceOS's own PyUI option-list renderer.

No SDL window is created by this app. Each selection is made by starting
Spruce's own MainUI in -optionListFile mode and letting it exit after a safe
one-line shell command records the selection. No SpruceOS files are edited.
"""
import json
import os
import shlex
import subprocess
import sys
import time
import traceback
from pathlib import Path

from nightlight_core import load_settings, discover_crtc, apply

APP = Path('/mnt/SDCARD/App/NightLight')
MENU = APP / 'nightlight-options.json'
CHOICE = APP / 'nightlight-choice.txt'
# PyUI writes EXIT here when the user presses B on the root menu.
PYUI_EXIT = Path('/mnt/SDCARD/App/PyUI/selection.txt')
MAINUI = '/mnt/SDCARD/spruce/flip/bin/MainUI'
MAIN_PY = '/mnt/SDCARD/App/PyUI/main-ui/mainui.py'
CFG = '/mnt/SDCARD/App/PyUI/py-ui-config.json'


def command(token):
    # Values in -optionListFile are shell commands: PyUI releases DRM master,
    # runs the command and exits automatically (see OptionSelectUI.run_action).
    return "printf '%s\\n' " + shlex.quote(token) + " > " + shlex.quote(str(CHOICE))


def menu_data(settings):
    state = 'ON' if settings['enabled'] else 'OFF'
    rows = {}
    rows['Warm light: ' + state] = command('TOGGLE')
    for key, name in [('intensity', 'Intensity'), ('amber', 'Orange tone')]:
        head = '{}: {}%'.format(name, settings[key])
        for amount in range(0, 101, 5):
            # Indicate the current value and show a textual slider as a preview.
            filled = amount // 10
            bar = '[' + '=' * filled + '-' * (10 - filled) + ']'
            mark = '* ' if amount == settings[key] else '  '
            label = '{}{:3d}% {}'.format(mark, amount, bar)
            rows[head + '/' + label] = command(key.upper() + '=' + str(amount))
    rows['APPLY & RETURN'] = command('APPLY')
    rows['CANCEL'] = command('CANCEL')
    rows['descriptions'] = {
        'Warm light: ' + state: 'Press A to toggle the filter',
        'Intensity: {}%'.format(settings['intensity']): 'Select the desired warmth level',
        'Orange tone: {}%'.format(settings['amber']): 'Select how amber the colour becomes',
        'APPLY & RETURN': 'Save and apply your chosen settings',
        'CANCEL': 'Leave without changes',
    }
    return rows


def atomic_write_json(path, obj):
    temp = str(path) + '.tmp'
    with open(temp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def get_selection(settings):
    # Reset selection markers; the original PyUI has already exited when our
    # launcher is called, so nothing else should be using this output path.
    for path in (CHOICE, PYUI_EXIT):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    atomic_write_json(MENU, menu_data(settings))
    args = [MAINUI, MAIN_PY,
            '-device', 'MIYOO_FLIP',
            '-logDir', '/mnt/SDCARD/Saves/spruce',
            '-pyUiConfig', CFG,
            '-cfwConfig', '/mnt/SDCARD/Saves/spruce/spruce-config.json',
            '-optionListFile', str(MENU),
            '-optionListTitle', 'NIGHT LIGHT']
    print('Opening SpruceOS native option menu...', flush=True)
    p = subprocess.Popen(args, cwd='/usr/miyoo/bin')
    started = time.monotonic()
    chosen = None
    try:
        while time.monotonic() - started < 180:
            if CHOICE.is_file():
                chosen = CHOICE.read_text(encoding='utf-8').strip()
                if chosen:
                    break
            # PyUI writes this marker if B exits the root menu rather than
            # selecting CANCEL. It does not automatically exit in that case.
            if PYUI_EXIT.is_file():
                if PYUI_EXIT.read_text(encoding='utf-8').strip() == 'EXIT':
                    chosen = 'CANCEL'
                    break
            if p.poll() is not None:
                # The command may have written a selection at the last instant.
                if CHOICE.is_file():
                    chosen = CHOICE.read_text(encoding='utf-8').strip()
                else:
                    print('Native menu exited early with code: %s' % p.returncode, flush=True)
                break
            time.sleep(.15)
    finally:
        if p.poll() is None:
            p.terminate()  # Only our OWN temporary menu subprocess.
            try:
                p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=3)
        for path in (CHOICE, PYUI_EXIT):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    if not chosen:
        print('Menu timed out or failed, no changes applied', flush=True)
        return 'CANCEL'
    print('Menu selected: %s' % chosen, flush=True)
    return chosen


def main():
    if not Path(MAINUI).is_file() or not Path(MAIN_PY).is_file():
        raise RuntimeError('Cannot locate the SpruceOS MainUI launcher/entrypoint')
    settings = load_settings()
    print('Night Light native menu settings: %s' % settings, flush=True)
    # Do not scan CRTC while a temporary menu holds DRM master.
    crtc = discover_crtc()
    print('Active CRTC: %r' % (crtc,), flush=True)
    for _ in range(60):
        choice = get_selection(settings)
        if choice == 'TOGGLE':
            settings['enabled'] = not settings['enabled']
        elif choice.startswith('INTENSITY=') or choice.startswith('AMBER='):
            name, value = choice.split('=', 1)
            try:
                val = int(value)
                if val % 5 != 0 or not 0 <= val <= 100:
                    raise ValueError('Out of range')
                settings[name.lower()] = val
            except ValueError:
                raise RuntimeError('Invalid value: ' + choice)
        elif choice == 'APPLY':
            # The menu process must be fully terminated before we open DRM.
            time.sleep(.3)
            apply(settings, crtc)
            print('SUCCESS: new Night Light settings applied', flush=True)
            return
        elif choice == 'CANCEL':
            print('Cancelled; original saved settings unchanged', flush=True)
            return
        else:
            raise RuntimeError('Invalid menu command: ' + choice)
    print('Exiting after 60 selections (safety cap)', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAILED: %s' % exc, flush=True)
        traceback.print_exc()
        sys.exit(1)
