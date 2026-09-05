"""Regression coverage for cancel, Back, directory completion and re-entry."""
import importlib
import json
import types
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import test_cleanui as fixture
from resources.lib.ui import controller


class LifecycleTests(unittest.TestCase):
    def test_cancelled_resume_returns_without_sixty_second_wait(self):
        ui = controller.UIController()
        calls, sleeps = [], []
        player = types.SimpleNamespace(isPlaying=lambda: False,
                                       isPlayingVideo=lambda: False)
        monitor = types.SimpleNamespace(abortRequested=lambda: False)
        with patch.object(fixture.xbmc, 'Player', return_value=player, create=True), \
             patch.object(fixture.xbmc, 'Monitor', return_value=monitor, create=True), \
             patch.object(fixture.xbmc, 'sleep', side_effect=sleeps.append), \
             patch.object(fixture.xbmc, 'executebuiltin', side_effect=lambda *a: calls.append(a)):
            self.assertFalse(ui._run_player('plugin://slyguy.max.cleanui/?play=test'))
        play = [x for x in calls if x[0].startswith('PlayMedia')]
        self.assertEqual(len(play), 1)
        self.assertTrue(play[0][1])
        self.assertLess(sum(sleeps), 1000)

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
            patch.object(fixture.gui, 'Window', return_value=self.owner, create=True),
            patch.object(fixture.slyguy, 'plugin', types.SimpleNamespace(Folder=Folder), create=True),
            patch.object(fixture.xbmc, 'executebuiltin', side_effect=self.commands.append),
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
        self.assertEqual(folder.items[0]['path'], 'plugin://slyguy.max.cleanui/')
        self.assertTrue(self.commands[-1].startswith('RunScript('))

    def test_launch_exit_clears_ownership_and_can_reopen(self):
        self.session.run('open_home')
        first = self.props[self.session.RUNNING]
        with patch.object(controller, 'UIController') as cls:
            self.session.launch(self.payload())
            cls.return_value.open_home.assert_called_once_with()
        self.assertNotIn(self.session.RUNNING, self.props)
        self.session.run('open_home')
        self.assertNotEqual(first, self.props[self.session.RUNNING])

    def test_duplicate_entry_does_not_schedule_second_ui(self):
        self.session.run('open_home')
        self.session.run('open_home')
        self.assertEqual(len(self.commands), 1)

    def test_cancel_start_profile_releases_owner_without_opening_home(self):
        self.session.run('open_home')
        with patch.object(controller, 'UIController') as cls:
            cls.return_value.select_start_profile.return_value = False
            self.session.launch(self.payload())
            cls.return_value.open_home.assert_not_called()
        self.assertNotIn(self.session.RUNNING, self.props)

    def test_launcher_keeps_addon_identity_and_library_extension(self):
        import xml.etree.ElementTree as ET
        manifest = ET.parse(fixture.ROOT / 'addon.xml').getroot()
        extension = manifest.find("extension[@point='xbmc.python.library']")
        self.assertEqual(extension.get('library'), 'ui.py')
        self.session.run('open_home')
        self.assertNotIn('.py', self.commands[-1])
        self.assertIn(self.session.xbmcaddon.Addon().getAddonInfo('id'), self.commands[-1])

    def test_failure_releases_lock(self):
        self.session.run('open_home')
        with patch.object(controller, 'UIController', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                self.session.launch(self.payload())
        self.assertNotIn(self.session.RUNNING, self.props)

    def test_route_arguments_survive_builtin_quoting(self):
        args = ['id with , "quotes" & accent é', '2']
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
