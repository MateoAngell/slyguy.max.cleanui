"""Regressions for remote focus and compact Kodi card layouts."""
import types
import unittest
import xml.etree.ElementTree as ET

import test_cleanui as support


class Control:
    def __init__(self, cid, count=0, item=None):
        self.cid = cid
        self.count = count
        self.position = 0 if count else -1
        self.item = item
        self.navigation = {}
        self.native_visible = False
        self.force_hidden = False
        self.condition = ''
        self.parent = None

    def size(self):
        return self.count

    def isVisible(self):
        return self.native_visible and not self.force_hidden

    def setVisible(self, visible):
        # Kodi only changes forceHidden here, not native m_visible.
        self.force_hidden = not visible

    def setVisibleCondition(self, condition):
        # Kodi handles literals synchronously. Expressions are evaluated
        # during a later render; registering one does not update m_visible.
        if condition in ('true', 'false'):
            self.native_visible = condition == 'true'
        else:
            self.condition = condition

    def getSelectedPosition(self):
        return self.position

    def selectItem(self, position):
        self.position = position

    def getSelectedItem(self):
        return self.item

    def controlUp(self, other):
        self.navigation['up'] = other.cid

    def controlDown(self, other):
        self.navigation['down'] = other.cid

    def controlLeft(self, other):
        self.navigation['left'] = other.cid

    def controlRight(self, other):
        self.navigation['right'] = other.cid


def window(kind, rails=(), actions=()):
    result = object.__new__(support.DetailWindow)
    result.screen = support.Screen(kind)
    result.controller = None
    result.properties = {}
    result.controls = {cid: Control(cid) for cid in (1000, 1001, 1002, 1003, 1004)}
    for i in range(support.C.MAX_RAILS_DETAIL):
        result.controls[6000 + i] = Control(6000 + i)
        result.controls[4000 + i] = Control(4000 + i, 2 if i in rails else 0)
        result.controls[4000 + i].parent = result.controls[6000 + i]
        result.properties['cleanui.detail.rail{}.visible'.format(i)] = (
            'true' if i in rails else 'false')
    for action in actions:
        result.properties['cleanui.detail.' + action] = 'available'
    result.getProperty = lambda key: result.properties.get(key, '')
    result.getControl = lambda cid: result.controls[cid]
    result.focused = 1003

    def dispatch_focus_before_render(control):
        # Model Kodi processing the queued focus message before a frame.
        # It silently rejects focus if CanFocus/parent visibility is false.
        if control.isVisible() and (control.parent is None or control.parent.isVisible()):
            result.focused = control.cid
    result.setFocus = dispatch_focus_before_render
    return result


class DetailFocusTests(unittest.TestCase):
    def test_seasons_focus_before_first_visible_frame(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0,), actions=('watchlist_action',))
        detail.controls[4000].position = -1
        detail._configure_navigation()
        detail._focus_best()
        self.assertEqual(detail.focused, 4000)
        self.assertEqual(detail.controls[4000].position, 0)

    def test_movie_prefers_play_over_recommendations(self):
        detail = window(support.C.SCREEN_MOVIE, rails=(0,), actions=('play_path',))
        detail._configure_navigation()
        detail._focus_best()
        self.assertEqual(detail.focused, 1000)

    def test_native_directions_skip_empty_rails_and_absent_actions(self):
        detail = window(support.C.SCREEN_SHOW, rails=(1, 3), actions=('play_path',))
        detail._configure_navigation()
        self.assertEqual(detail.controls[1003].navigation['right'], 1000)
        self.assertEqual(detail.controls[1000].navigation['left'], 1003)
        self.assertEqual(detail.controls[1003].navigation['down'], 4001)
        self.assertEqual(detail.controls[1000].navigation['down'], 4001)
        self.assertEqual(detail.controls[4001].navigation, {'up': 1000, 'down': 4003})
        self.assertEqual(detail.controls[4003].navigation, {'up': 4001, 'down': 4003})

    def test_empty_screen_retains_back_button(self):
        detail = window(support.C.SCREEN_SHOW)
        detail._configure_navigation()
        detail._focus_best()
        self.assertEqual(detail.focused, 1003)
        self.assertTrue(all(cid == 1003 for cid in detail.controls[1003].navigation.values()))

    def test_restored_hidden_action_is_rejected(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0,))
        detail.screen._cleanui_window_state = {'focus_id': 1002, 'positions': {}}
        self.assertFalse(detail._restore_state())

    def test_restore_clamps_episode_position_before_render(self):
        detail = window(support.C.SCREEN_SEASON, rails=(0,))
        detail.screen._cleanui_window_state = {'focus_id': 4000, 'positions': {4000: 99}}
        detail._configure_navigation()
        self.assertTrue(detail._restore_state())
        self.assertEqual(detail.focused, 4000)
        self.assertEqual(detail.controls[4000].position, 1)

    def test_reused_page_hides_old_controls_before_next_frame(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0, 1), actions=('play_path',))
        detail._configure_navigation()
        self.assertTrue(detail.controls[4000].isVisible())
        self.assertTrue(detail.controls[6000].isVisible())
        self.assertTrue(detail.controls[1000].isVisible())
        detail.properties['cleanui.detail.rail0.visible'] = 'false'
        detail.properties['cleanui.detail.play_path'] = ''
        detail._configure_navigation()
        self.assertFalse(detail.controls[4000].isVisible())
        self.assertFalse(detail.controls[6000].isVisible())
        self.assertFalse(detail.controls[1000].isVisible())
        self.assertTrue(detail.controls[4001].isVisible())
        self.assertIn('rail0.visible', detail.controls[4000].condition)
        detail._focus_best()
        self.assertEqual(detail.focused, 4001)

    def test_invalid_selection_never_activates_last_season(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0,))
        detail.screen.rails = [support.Rail(items=[support.Card(kind='season')])]
        detail.controls[4000].position = -1
        detail.controls[4000].getSelectedItem = lambda: self.fail('Invalid selection must stop')
        detail._open_selected(4000)

    def test_selected_season_opens_through_cleanui_controller(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0,))
        card = support.Card(kind='season', show_id='show', season_id='2')
        detail.screen.rails = [support.Rail(items=[card])]
        properties = {'cleanui.kind': 'season', 'cleanui.show_id': 'show', 'cleanui.season_id': '2'}
        detail.controls[4000].item = types.SimpleNamespace(
            getProperty=lambda key: properties.get(key, ''))
        opened = []
        detail.controller = types.SimpleNamespace(open_season=lambda *args: opened.append(args))
        detail._open_selected(4000)
        self.assertEqual(opened, [('show', '2')])

    def test_native_click_and_delayed_select_open_only_one_season(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0,))
        detail._last_activation = None
        detail.getFocusId = lambda: 4000
        opened = []
        detail._open_selected = lambda cid: opened.append(cid)
        detail.onClick(4000)
        # Simulate a slow modal/API call exhausting the old 0.6s debounce.
        detail._last_activation = ((4000, 0), 0)
        detail.onAction(types.SimpleNamespace(getId=lambda: 7))
        self.assertEqual(opened, [4000])

    def test_back_button_click_and_select_pop_only_one_page(self):
        detail = window(support.C.SCREEN_SHOW, rails=(0,))
        detail.getFocusId = lambda: 1003
        popped = []
        detail._close_current_window = lambda: popped.append(True)
        detail.onClick(1003)
        detail.onAction(types.SimpleNamespace(getId=lambda: 7))
        self.assertEqual(popped, [True])


class CompactLayoutTests(unittest.TestCase):
    def layouts(self):
        for name in ('uihome.xml', 'ui_detail.xml'):
            yield name, ET.parse(support.ROOT / 'resources/skins/Default/1080i' / name)

    def test_empty_detail_groups_do_not_reserve_vertical_space(self):
        root = ET.parse(support.ROOT / 'resources/skins/Default/1080i/ui_detail.xml')
        for i in range(support.C.MAX_RAILS_DETAIL):
            group = root.find('.//control[@id="{}"]'.format(6000 + i))
            self.assertIn('detail.rail{}.visible'.format(i), group.findtext('visible'))

    def test_card_content_stays_inside_compact_slot(self):
        for name, root in self.layouts():
            for rail in root.findall('.//control[@type="fixedlist"]'):
                for tag in ('itemlayout', 'focusedlayout'):
                    for layout in rail.findall(tag):
                        width, height = int(layout.get('width')), int(layout.get('height'))
                        self.assertIn(width, (212, 308), (name, rail.get('id')))
                        for control in layout.findall('control'):
                            x, y = int(control.findtext('left')), int(control.findtext('top'))
                            w, h = int(control.findtext('width')), int(control.findtext('height'))
                            self.assertGreaterEqual(x, 0)
                            self.assertGreaterEqual(y, 0)
                            self.assertLessEqual(x + w, width)
                            self.assertLessEqual(y + h, height)

    def test_movie_and_show_cards_have_no_name_overlay(self):
        for name, root in self.layouts():
            for rail in root.findall('.//control[@type="fixedlist"]'):
                for control in rail.findall('.//control[@type="label"]'):
                    visible = control.findtext('visible') or ''
                    if visible == 'String.IsEqual(ListItem.Property(cleanui.kind),episode)':
                        continue
                    self.assertIn('!String.IsEqual(ListItem.Property(cleanui.kind),movie)', visible, name)
                    self.assertIn('!String.IsEqual(ListItem.Property(cleanui.kind),show)', visible, name)

    def test_only_actual_focused_row_gets_white_frame(self):
        for name, root in self.layouts():
            for rail in root.findall('.//control[@type="fixedlist"]'):
                for control in rail.findall('.//focusedlayout/control'):
                    texture = control.find('texture')
                    if texture is not None and texture.get('colordiffuse') == 'FFFFFFFF':
                        self.assertEqual(control.findtext('visible'),
                                         'Control.HasFocus({})'.format(rail.get('id')), name)


if __name__ == '__main__':
    unittest.main()
