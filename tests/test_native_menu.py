import sys
import threading
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import native_menu
from nightlight_core import DEFAULT


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class MenuTests(unittest.TestCase):
    def test_display_discovery_overlaps_imports_and_finishes_before_return(self):
        discovery_started = threading.Event()
        imports_started = threading.Event()
        discovery_finished = threading.Event()
        runtime = module('mainui')

        def discover():
            discovery_started.set()
            if not imports_started.wait(timeout=2):
                raise AssertionError('Imports did not overlap display discovery')
            discovery_finished.set()
            return (1, 2, 1024)

        def import_runtime(name):
            self.assertEqual(name, 'mainui')
            self.assertTrue(discovery_started.wait(timeout=2))
            imports_started.set()
            return runtime

        with patch.object(native_menu, 'discover_crtc', side_effect=discover), \
                patch.object(native_menu.importlib, 'import_module', side_effect=import_runtime):
            result = native_menu.load_runtime()
        self.assertEqual(result, (runtime, (1, 2, 1024)))
        self.assertTrue(discovery_finished.is_set())

    def test_display_discovery_failure_prevents_ui_startup(self):
        runtime = module('mainui', main=Mock())
        with patch.dict(sys.modules, {'mainui': runtime}), \
                patch.object(native_menu, 'MAIN_PY') as path, \
                patch.object(native_menu, 'load_settings', return_value=dict(DEFAULT)), \
                patch.object(native_menu, 'discover_crtc', side_effect=RuntimeError('No CRTC')), \
                patch.object(sys, 'path', list(sys.path)):
            path.is_file.return_value = True
            path.parent = '/fake/pyui'
            with self.assertRaisesRegex(RuntimeError, 'No CRTC'):
                native_menu.main()
        runtime.main.assert_not_called()

    def run_menu(self, actions, initial=None):
        settings = dict(DEFAULT if initial is None else initial)
        views = []
        actions = iter(actions)
        created = []

        def create_view(**kwargs):
            created.append(kwargs)
            state = dict(kwargs)

            def set_options(options):
                state['options'] = options

            def get_selection(buttons):
                self.assertIn('LEFT', buttons)
                self.assertIn('RIGHT', buttons)
                views.append(dict(state))
                index, button = next(actions)
                if index is not None:
                    state['selected_index'] = index
                if button in ('DOWN', 'UP'):
                    direction = 1 if button == 'DOWN' else -1
                    state['selected_index'] = (state['selected_index'] + direction) % len(state['options'])
                    # Real ListView consumes arrows internally and returns a
                    # Selection with input=None, preserving its new index.
                    button = None
                selected_index = state['selected_index']
                return SimpleNamespace(
                    get_input=lambda: button, get_index=lambda: selected_index,
                    get_selection=lambda: state['options'][selected_index])

            return SimpleNamespace(get_selection=get_selection, set_options=set_options)

        def entry(**kwargs):
            return SimpleNamespace(**kwargs, get_value=lambda: kwargs['value'])

        modules = {
            'controller.controller_inputs': module('controller.controller_inputs',
                                                   ControllerInput=SimpleNamespace(A='A', B='B', DPAD_LEFT='LEFT', DPAD_RIGHT='RIGHT')),
            'views.grid_or_list_entry': module('views.grid_or_list_entry', GridOrListEntry=entry),
            'views.view_creator': module('views.view_creator', ViewCreator=SimpleNamespace(create_view=create_view)),
            'views.view_type': module('views.view_type', ViewType=SimpleNamespace(ICON_AND_DESC=1)),
        }
        with patch.dict(sys.modules, modules):
            result = native_menu.edit_settings(settings)
        self.assertEqual(len(created), 1, 'Keep the same view across input cycles')
        return result, settings, views

    def test_arrows_and_idle_frames_preserve_highlight(self):
        result, settings, views = self.run_menu([
            (None, 'DOWN'), (None, 'DOWN'), (None, None),
            (None, 'UP'), (None, 'RIGHT'),
            (None, None), (None, 'DOWN'), (None, 'DOWN'), (None, 'A'),
        ])
        self.assertTrue(result)
        self.assertEqual(settings, dict(DEFAULT, intensity=55))
        self.assertEqual([v['selected_index'] for v in views], [0, 1, 2, 2, 1, 1, 1, 2, 3])

    def test_up_wraps_to_cancel(self):
        result, _, views = self.run_menu([(None, 'UP'), (None, 'A')])
        self.assertFalse(result)
        self.assertEqual(views[-1]['selected_index'], 4)

    def test_edits_stay_in_menu_until_apply(self):
        result, settings, views = self.run_menu(
            [(0, 'A'), (1, 'RIGHT'), (2, 'LEFT'), (3, 'A')])
        self.assertTrue(result)
        self.assertEqual(settings, dict(enabled=True, intensity=55, amber=45))
        self.assertEqual(views[1]['options'][0].value_text, '<    ON    >')
        self.assertEqual(views[2]['options'][1].value_text, '<    55%    >')
        self.assertEqual(views[3]['options'][2].value_text, '<    45%    >')
        self.assertEqual([o.primary_text for o in views[0]['options']],
                         ['Warm light', 'Intensity', 'Orange tone', 'Apply & Exit', 'Discard & Exit'])
        self.assertEqual([v['selected_index'] for v in views], [0, 0, 1, 2])

    def test_a_on_percentage_does_not_open_a_submenu_or_change_value(self):
        result, settings, _ = self.run_menu([(1, 'A'), (2, 'A'), (3, 'A')])
        self.assertTrue(result)
        self.assertEqual(settings, DEFAULT)

    def test_cancel_and_root_back_discard_edits(self):
        for action in [(4, 'A'), (0, 'B')]:
            result, _, _ = self.run_menu([(0, 'A'), action])
            self.assertFalse(result)

    def test_percentages_stop_at_bounds(self):
        for initial, button, expected in [(98, 'RIGHT', 100), (100, 'RIGHT', 100),
                                           (2, 'LEFT', 0), (0, 'LEFT', 0)]:
            result, settings, _ = self.run_menu(
                [(1, button), (2, button), (3, 'A')],
                dict(DEFAULT, intensity=initial, amber=initial))
            self.assertTrue(result)
            self.assertEqual(settings['intensity'], expected)
            self.assertEqual(settings['amber'], expected)

    def test_arrows_toggle_filter_but_do_not_activate_exit_rows(self):
        result, settings, _ = self.run_menu([
            (0, 'RIGHT'), (0, 'LEFT'), (3, 'RIGHT'), (4, 'LEFT'), (3, 'A')])
        self.assertTrue(result)
        self.assertFalse(settings['enabled'])

    def test_display_closes_before_apply_and_cancel_never_applies(self):
        for should_apply in [True, False]:
            events = []
            runtime = module('mainui')
            runtime.main = lambda: runtime.check_for_option_list_file(None)
            sdl = module('sdl2', SDL_Quit=lambda: events.append('close'))
            with patch.dict(sys.modules, {
                'mainui': runtime,
                'sdl2': sdl,
            }), patch.object(native_menu, 'MAIN_PY') as path, \
                    patch.object(native_menu, 'load_settings', return_value=dict(DEFAULT)), \
                    patch.object(native_menu, 'discover_crtc', return_value=(1, 2, 1024)), \
                    patch.object(native_menu, 'edit_settings', return_value=should_apply), \
                    patch.object(native_menu, 'apply', side_effect=lambda *args: events.append('apply')), \
                    patch.object(sys, 'path', list(sys.path)):
                path.is_file.return_value = True
                path.parent = '/fake/pyui'
                with self.assertRaises(SystemExit) as exit_result:
                    native_menu.main()
                self.assertEqual(exit_result.exception.code, 0)
            self.assertEqual(events, ['close', 'apply'] if should_apply else ['close'])

    def test_failure_still_releases_display_without_applying(self):
        runtime = module('mainui')
        runtime.main = lambda: runtime.check_for_option_list_file(None)
        sdl = module('sdl2', SDL_Quit=Mock())
        with patch.dict(sys.modules, {
            'mainui': runtime,
            'sdl2': sdl,
        }), patch.object(native_menu, 'MAIN_PY') as path, \
                patch.object(native_menu, 'load_settings', return_value=dict(DEFAULT)), \
                patch.object(native_menu, 'discover_crtc', return_value=(1, 2, 1024)), \
                patch.object(native_menu, 'edit_settings', side_effect=RuntimeError('UI failed')), \
                patch.object(native_menu, 'apply') as apply, \
                patch.object(sys, 'path', list(sys.path)):
            path.is_file.return_value = True
            path.parent = '/fake/pyui'
            with self.assertRaisesRegex(RuntimeError, 'UI failed'):
                native_menu.main()
            sdl.SDL_Quit.assert_called_once()
            apply.assert_not_called()

    def test_success_flushes_logs_before_fast_process_exit(self):
        events = []
        with patch.object(native_menu, 'main', side_effect=SystemExit(0)), \
                patch.object(sys, 'stdout', SimpleNamespace(flush=lambda: events.append('stdout'))), \
                patch.object(sys, 'stderr', SimpleNamespace(flush=lambda: events.append('stderr'))), \
                patch.object(native_menu.os, '_exit', side_effect=lambda code: events.append(('exit', code))):
            native_menu.run()
        self.assertEqual(events, ['stdout', 'stderr', ('exit', 0)])

    def test_failure_keeps_error_status_and_does_not_fast_exit_successfully(self):
        with patch.object(native_menu, 'main', side_effect=RuntimeError('Apply failed')), \
                patch.object(native_menu.traceback, 'print_exc'), \
                patch.object(native_menu.os, '_exit') as fast_exit:
            with self.assertRaises(SystemExit) as result:
                native_menu.run()
            self.assertEqual(result.exception.code, 1)
            fast_exit.assert_not_called()

    def test_nonzero_exit_is_preserved(self):
        with patch.object(native_menu, 'main', side_effect=SystemExit(2)), \
                patch.object(native_menu.os, '_exit') as fast_exit:
            with self.assertRaises(SystemExit) as result:
                native_menu.run()
            self.assertEqual(result.exception.code, 2)
            fast_exit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
