"""Selection regressions using Kodi's native-navigation-before-Python order.

The real HomeWindow class executes against lightweight GUI controls. No Kodi,
network, playback or SlyGuy authentication is simulated here. The second suite
also runs against the Disney hotfix when that sibling checkout is available.
"""
import ast
from pathlib import Path
import runpy
import time
import traceback
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAX_HOME = ROOT / 'resources/lib/ui/home_window.py'
DISNEY_HOME = ROOT.parent / 'disney/resources/lib/ui/home_window.py'
C = types.SimpleNamespace(**runpy.run_path(str(ROOT / 'resources/lib/ui/constants.py')))


class Control:
    def __init__(self, control_id):
        self.control_id = control_id
        self.items = []
        self.position = 0
        self.reads = 0
        self.after_read = None

    def getSelectedPosition(self):
        self.reads += 1
        current = self.position
        if self.after_read:
            self.after_read(self)
        return current

    def selectItem(self, position):
        self.position = position

    def size(self):
        return len(self.items)

    def reset(self):
        self.items = []
        self.position = 0

    def addItems(self, items):
        self.items.extend(items)

    def setHeight(self, height):
        self.height = height


class Dialog:
    def __init__(self, *args, **kwargs):
        ids = list(range(4000, 4024)) + list(range(6000, 6024))
        ids += [4101, C.CONTROL_PROFILE, C.CONTROL_MENU]
        self.controls = {i: Control(i) for i in ids}
        self.focus_id = 4000
        self.properties = {}
        self.property_writes = 0

    def getFocusId(self):
        return self.focus_id

    def getControl(self, control_id):
        if control_id not in self.controls:
            raise RuntimeError('Control unavailable')
        return self.controls[control_id]

    def setFocus(self, control):
        self.focus_id = control.control_id

    def setProperty(self, name, value):
        self.properties[name] = value
        self.property_writes += 1

    def getProperty(self, name):
        return self.properties.get(name, '')

    def close(self):
        self.closed = True


def card(name):
    return types.SimpleNamespace(
        label=name, kind='movie', art={'fanart': name + '.jpg'},
        info={'plot': 'Plot ' + name},
    )


def screen(names):
    cards = [card(name) for name in names]
    return types.SimpleNamespace(
        hero=cards[0] if cards else None,
        rails=[types.SimpleNamespace(items=cards, style='poster', title='Movies', rail_id='movies')],
    )


def load_window(path):
    source = ast.parse(path.read_text(encoding='utf-8'))
    window_class = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'HomeWindow')
    xbmc = types.SimpleNamespace(log=lambda *args: None, sleep=lambda *args: None,
                                 LOGINFO=1, LOGERROR=2, LOGWARNING=3, LOGDEBUG=4)
    adapter = types.SimpleNamespace(
        _effective_rail_style=lambda rail, kind: rail.style,
        to_list_item=lambda item, style: item if item.label != 'Broken' else None,
    )
    namespace = dict(C=C, xbmc=xbmc, xbmcgui=types.SimpleNamespace(WindowXMLDialog=Dialog),
                     UIAdapter=adapter, userdata={}, time=time, traceback=traceback)
    exec(compile(ast.Module(body=[window_class], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['HomeWindow']


class HeroCases:
    path = MAX_HOME

    def setUp(self):
        self.window = load_window(self.path)(screen=screen(['First', 'Second', 'Third', 'Fourth']))
        self.window._populate()
        self.window._refresh_hero_from_focus()

    def action(self, action_id, position, control_id=4000):
        # Kodi applies movement in C++ BEFORE delivering WindowXML.onAction.
        self.window.focus_id = control_id
        self.window.getControl(control_id).position = position
        self.window.onAction(types.SimpleNamespace(getId=lambda: action_id))

    def assert_hero(self, name):
        self.assertEqual(self.window.getProperty('cleanui.hero.title'), name)
        self.assertEqual(self.window.getProperty('cleanui.hero.plot'), 'Plot ' + name)
        self.assertEqual(self.window.getProperty('cleanui.hero.fanart'), name + '.jpg')

    def test_second_card_is_second_after_native_right(self):
        self.action(2, 1)
        self.assert_hero('Second')

    def test_left_does_not_subtract_from_already_updated_selection(self):
        self.action(1, 2)
        self.assert_hero('Third')

    def test_held_remote_and_boundaries_never_predict_outside_selection(self):
        for position in (1, 2, 3, 3, 2, 1, 0, 0):
            self.action(2 if position >= self.window.getControl(4000).position else 1, position)
            self.assert_hero(('First', 'Second', 'Third', 'Fourth')[position])

    def test_page_jump_and_mouse_selection_use_actual_index(self):
        self.action(6, 3)
        self.assert_hero('Fourth')
        self.action(107, 1)
        self.assert_hero('Second')

    def test_vertical_rail_change_without_focus_callback(self):
        self.window.screen.rails.append(types.SimpleNamespace(items=[card('Other rail')]))
        self.action(4, 0, 4001)
        self.assert_hero('Other rail')

    def test_legacy_poster_rail_maps_to_second_model_rail(self):
        self.window.screen.rails.append(types.SimpleNamespace(items=[card('Poster rail')]))
        self.action(4, 0, 4101)
        self.assert_hero('Poster rail')

    def test_read_position_once_so_key_cannot_skip_a_rapid_selection(self):
        control = self.window.getControl(4000)
        control.position = 1
        control.reads = 0
        control.after_read = lambda c: setattr(c, 'position', 2)
        self.window._refresh_hero_from_focus()
        self.assertEqual(control.reads, 1)
        self.assert_hero('Second')
        control.after_read = None
        self.window._refresh_hero_from_focus()
        self.assert_hero('Third')

    def test_unchanged_focus_does_not_reload_images_or_rewrite_properties(self):
        writes = self.window.property_writes
        for _ in range(10):
            self.window._refresh_hero_from_focus()
        self.assertEqual(self.window.property_writes, writes)

    def test_card_replaced_at_same_position_is_not_deduplicated(self):
        self.window.screen.rails[0].items[0] = card('New screen')
        self.window._refresh_hero_from_focus()
        self.assert_hero('New screen')

    def test_filtered_invalid_card_cannot_offset_hero(self):
        self.window.screen = screen(['First', 'Broken', 'Second', 'Third'])
        self.window._populate()
        self.action(2, 1)
        self.assert_hero('Second')
        self.assertEqual(len(self.window.screen.rails[0].items), 3)

    def test_click_opens_the_same_card_that_the_hero_describes(self):
        self.action(2, 1)
        opened = []
        self.window._activate_control = lambda control_id: opened.append(self.window._selected_card(control_id))
        self.window.onClick(4000)
        self.assertEqual(opened[0].label, self.window.getProperty('cleanui.hero.title'))

    def test_focus_on_header_or_removed_control_keeps_hero_without_failure(self):
        self.action(3, 0, C.CONTROL_PROFILE)
        self.assert_hero('First')
        self.window.focus_id = 99999
        self.window._refresh_hero_from_focus()
        self.assert_hero('First')

    def test_delayed_select_callback_does_not_reopen_movie(self):
        movie = self.window.screen.rails[0].items[0]
        movie.deeplink_id, movie.show_id, movie.season_id = 'first', None, None
        opened = []
        self.window.controller = types.SimpleNamespace(open_movie=lambda *args: opened.append(args))
        self.window.onClick(4000)
        # The first callback's modal/API operation took longer than the old
        # 600ms duplicate guard; Kodi now delivers the same key's onAction.
        self.window._last_activation = ((4000, 0), time.monotonic() - 2)
        self.window.onAction(types.SimpleNamespace(getId=lambda: 7))
        self.assertEqual(len(opened), 1)

    def test_select_after_screen_replacement_cannot_activate_new_focus(self):
        opened = []
        def movies(source):
            opened.append('movies')
            self.window._last_activation = None
            self.window.focus_id = C.CONTROL_SERIES
        self.window.controller = types.SimpleNamespace(
            open_movies=movies, open_series=lambda source: opened.append('series'))
        self.window.focus_id = C.CONTROL_MOVIES
        self.window.onClick(C.CONTROL_MOVIES)
        self.window.onAction(types.SimpleNamespace(getId=lambda: 7))
        self.assertEqual(opened, ['movies'])

    def test_mouse_click_is_activated_only_once(self):
        opened = []
        self.window._activate_control = lambda control_id: opened.append(control_id)
        self.window.onClick(4000)
        self.window.onAction(types.SimpleNamespace(getId=lambda: 100))
        self.assertEqual(opened, [4000])

    def test_context_menu_action_remains_available(self):
        opened = []
        self.window._activate_control = lambda control_id: opened.append(control_id)
        self.window.onAction(types.SimpleNamespace(getId=lambda: C.ACTION_MENU[0]))
        self.assertEqual(opened, [C.CONTROL_MENU])


class MaxHeroTests(HeroCases, unittest.TestCase):
    path = MAX_HOME

    def test_back_from_more_home_categories_restores_parent_before_exit(self):
        previous = screen(['Previous category page'])
        events = []
        self.window.controller = types.SimpleNamespace(
            _home_stack=[(previous, 'home')],
            exit_clean_ui=lambda: events.append('exit'),
            close_child_window=lambda window: events.append('close'))
        self.window.replace_screen = lambda target, kind: events.append((target, kind))
        self.window.onAction(types.SimpleNamespace(getId=lambda: C.ACTION_BACK[0]))
        self.assertEqual(events, [(previous, 'home')])
        self.assertEqual(self.window.controller._home_stack, [])

    def test_back_from_root_home_still_exits(self):
        events = []
        self.window.controller = types.SimpleNamespace(
            _home_stack=[], exit_clean_ui=lambda: events.append('exit'))
        self.window.onAction(types.SimpleNamespace(getId=lambda: C.ACTION_BACK[0]))
        self.assertEqual(events, ['exit'])

    def test_row_dimensions_follow_effective_artwork_style(self):
        self.window.screen.rails[0].style = 'landscape'
        self.window._populate()
        self.assertEqual(self.window.getControl(6000).height, 266)
        self.assertEqual(self.window.getControl(4000).height, 220)
        self.assertEqual(self.window.getProperty('cleanui.home.rail0.style'), 'landscape')
        self.window.screen.rails[0].style = 'poster'
        self.window._populate()
        self.assertEqual(self.window.getControl(6000).height, 362)
        self.assertEqual(self.window.getControl(4000).height, 316)


@unittest.skipUnless(DISNEY_HOME.exists(), 'Disney sibling checkout unavailable')
class DisneyHeroTests(HeroCases, unittest.TestCase):
    path = DISNEY_HOME


if __name__ == '__main__':
    unittest.main()
