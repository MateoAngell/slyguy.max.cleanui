"""Regression coverage for cancel, Back, directory completion and re-entry."""
import importlib
import json
import types
import unittest
from unittest.mock import patch
from urllib.parse import quote, unquote

import test_cleanui as fixture
from resources.lib.ui import controller


class LifecycleTests(unittest.TestCase):
    def test_playback_delegates_to_event_observer_and_preserves_transition(self):
        from resources.lib.ui import playback
        ui = controller.UIController()
        with patch.object(playback, 'observe_playback', return_value=True) as observe:
            self.assertTrue(ui._run_player('plugin://slyguy.max.cleanui/?play=test'))
        self.assertEqual(observe.call_count, 1)
        self.assertEqual(observe.call_args.args, ('plugin://slyguy.max.cleanui/?play=test',))
        self.assertEqual(observe.call_args.kwargs['on_started'], ui.end_transition)
        self.assertFalse(observe.call_args.kwargs['cancelled']())
        ui.exit_requested = True
        self.assertTrue(observe.call_args.kwargs['cancelled']())

    def test_back_with_live_parent_never_creates_black_modal_after_playback(self):
        ui = controller.UIController()
        parent = types.SimpleNamespace(close=lambda: None)
        closed = []
        child = types.SimpleNamespace(close=lambda: closed.append(True))
        ui._windows = [parent, child]
        ui._processing_playback = True
        with patch.object(controller, '_TransitionCurtain') as curtain:
            ui.close_child_window(child)
            curtain.assert_not_called()
        self.assertEqual(closed, [True])
        self.assertIsNone(ui._transition_curtain)

    def test_transition_cannot_wait_for_missing_focus_callback(self):
        ui = controller.UIController()
        with patch.object(controller, '_TransitionCurtain') as curtain:
            ui.begin_transition()
            curtain.assert_not_called()
        self.assertIsNone(ui._transition_curtain)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.props, self.commands = {}, []
        self.owner = types.SimpleNamespace(
            getProperty=lambda key: self.props.get(key, ''),
            setProperty=lambda key, value: self.props.update({key: value}),
            clearProperty=lambda key: self.props.pop(key, None))
        class Folder:
            def __init__(self, **kw):
                self.items = []
            def add_item(self, **kw):
                self.items.append(kw)
        self.patches = [
            patch('resources.lib.ui.entry.capture_origin', return_value=dict(window=1100, path='', focus=0)),
            patch.object(fixture.gui, 'getCurrentWindowId', return_value=10025, create=True),
            patch('resources.lib.ui.intro.start', return_value=types.SimpleNamespace(
                cancelled=False, close=lambda: None)),
            patch.object(fixture.gui, 'Window', return_value=self.owner, create=True),
            patch.object(fixture.slyguy, 'plugin', types.SimpleNamespace(
                Folder=Folder, resolve=lambda: self.commands.append('resolve-directory')), create=True),
            patch.object(fixture.xbmc, 'executebuiltin', side_effect=lambda command, wait=False: self.commands.append(command)),
            patch.object(fixture.xbmc, 'getSkinDir', return_value='skin.estuary', create=True),
            patch.object(fixture.core, 'before_dispatch', create=True),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.session = importlib.import_module('resources.lib.ui.session')
        self.session = importlib.reload(self.session)

    def payload(self):
        return self.commands[-1].split('","', 1)[1][:-2]

    def test_directory_returns_before_ui_and_fallback_is_not_internal_files(self):
        with patch.object(controller, 'UIController') as cls:
            folder = self.session.run('open_home')
            cls.assert_not_called()
        self.assertEqual(folder.items, [])
        self.assertTrue(self.commands[-1].startswith('RunScript('))
        folder.display()
        self.assertEqual(self.commands[-1], 'resolve-directory')

    def test_launch_exit_clears_ownership_and_can_reopen(self):
        self.session.run('open_home')
        first = self.props[self.session.RUNNING]
        with patch.object(controller, 'UIController') as cls:
            self.session.launch(self.payload())
            cls.return_value.open_home.assert_called_once_with()
        self.assertNotIn(self.session.RUNNING, self.props)
        self.session.run('open_home')
        self.assertNotEqual(first, self.props[self.session.RUNNING])

    def test_exit_navigation_follows_base_release_once(self):
        startup = types.SimpleNamespace(cancelled=False,
            close=lambda: self.commands.append('close-base'))
        with patch('resources.lib.ui.intro.start', return_value=startup), \
             patch.object(controller, 'UIController'):
            self.session.run('open_home')
            self.session.launch(self.payload())
        self.assertEqual(self.commands[-2:], ['close-base', 'ReplaceWindow(1100)'])
        self.assertEqual(self.commands.count('ReplaceWindow(1100)'), 1)

    def test_other_skin_restores_captured_origin_not_fixed_home(self):
        with patch.object(fixture.xbmc, 'getSkinDir', return_value='other.skin'), \
             patch.object(controller, 'UIController'):
            self.session.run('open_home')
            self.session.launch(self.payload())
        self.assertEqual(self.commands[-1], 'ReplaceWindow(1100)')

    def test_duplicate_entry_does_not_schedule_second_ui(self):
        self.session.run('open_home')
        self.session.run('open_home')
        self.assertEqual(len(self.commands), 1)

    def test_cancel_start_profile_releases_owner_after_opening_shell(self):
        with patch.object(controller, 'UIController') as cls:
            self.session.run('open_home')
            self.session.launch(self.payload())
            cls.return_value.open_home.assert_called_once_with()
            cls.return_value.select_start_profile.assert_not_called()
        self.assertNotIn(self.session.RUNNING, self.props)

    def test_initial_home_builds_catalog_after_profile_is_resolved(self):
        ui = controller.UIController()
        with patch.object(ui.repository, 'build_home') as build_home:
            ui._load_initial_home()
        build_home.assert_called_once_with()

    def test_cancelled_profile_never_creates_home_window(self):
        ui = controller.UIController()
        with patch.object(ui, 'select_start_profile', return_value=False), \
             patch.object(controller, 'HomeWindow') as home:
            self.assertFalse(ui.open_home())
        home.assert_not_called()

    def test_playback_closes_clean_ui_before_resolver_and_restores_stack(self):
        closed = []

        class RootHome:
            def __init__(self):
                self.screen = object()
            def capture_state(self):
                pass

        root = RootHome()
        child = types.SimpleNamespace(
            screen=object(),
            capture_state=lambda: None,
            close=lambda: closed.append(True),
        )
        ui = controller.UIController()
        ui._windows = [root, child]
        with patch.object(controller, 'HomeWindow', RootHome):
            self.assertTrue(ui.play('plugin://slyguy.max.cleanui/?play=test'))
        self.assertEqual(closed, [True])
        self.assertEqual(ui._pending_playback['screens'], [root.screen, child.screen])

    def test_launcher_keeps_addon_identity_and_library_extension(self):
        import xml.etree.ElementTree as ET
        manifest = ET.parse(fixture.ROOT / 'addon.xml').getroot()
        extension = manifest.find("extension[@point='xbmc.python.library']")
        self.assertEqual(extension.get('library'), 'ui.py')
        self.session.run('open_home')
        self.assertNotIn('.py', self.commands[-1])
        self.assertIn(self.session.xbmcaddon.Addon().getAddonInfo('id'), self.commands[-1])

    def test_failure_releases_lock(self):
        with patch.object(controller, 'UIController', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                self.session.run('open_home')
                self.session.launch(self.payload())
        self.assertNotIn(self.session.RUNNING, self.props)

    def test_intro_precedes_initialization_and_closes_at_session_end(self):
        events = []
        startup = types.SimpleNamespace(cancelled=False, close=lambda: events.append('close'))
        with patch('resources.lib.ui.intro.start', side_effect=lambda *a: events.append('intro') or startup), \
             patch.object(fixture.core, 'before_dispatch', side_effect=lambda: events.append('initialize')), \
             patch.object(controller, 'UIController') as cls:
            cls.return_value.open_home.side_effect = lambda: events.append('home')
            self.session.run('open_home')
            self.session.launch(self.payload())
        self.assertEqual(events, ['intro', 'initialize', 'home', 'close'])
        self.assertNotIn(self.session.RUNNING, self.props)

    def test_intro_cancel_never_opens_controller_and_releases_owner(self):
        startup = types.SimpleNamespace(cancelled=True, close=lambda: None)
        with patch('resources.lib.ui.intro.start', return_value=startup), \
             patch.object(controller, 'UIController') as cls:
            self.session.run('open_home')
            self.session.launch(self.payload())
            cls.assert_not_called()
        self.assertNotIn(self.session.RUNNING, self.props)

    def test_route_arguments_survive_builtin_quoting(self):
        args = ['id with , "quotes" & accent é', '2']
        with patch.object(controller, 'UIController') as cls:
            self.session.run('open_season', *args)
            method, decoded, token = json.loads(unquote(self.payload()))
            self.assertEqual((method, decoded), ('open_season', args))
            self.assertEqual(token, self.props[self.session.RUNNING])

    def test_stale_launcher_cannot_clear_new_owner(self):
        self.session.run('open_home')
        payload = self.payload()
        self.props[self.session.RUNNING] = 'another-owner'
        with patch.object(controller, 'UIController') as cls:
            self.session.launch(payload)
            cls.assert_not_called()
        self.assertEqual(self.props[self.session.RUNNING], 'another-owner')

    def test_invisible_owner_is_not_reclaimed_during_playback(self):
        self.props[self.session.RUNNING] = 'dead-owner'
        self.props[self.session.RUNNING_SINCE] = '1'
        self.session.run('open_home')
        self.assertEqual(self.props[self.session.RUNNING], 'dead-owner')
        self.assertEqual(len(self.commands), 0)
