"""Offline regression tests using the unchanged SlyGuy item parser.

These exercise catalog/UI contracts, not live service authentication or DRM.
Run: python -m unittest discover -s tests -v
"""
import ast
import contextlib
import copy
import importlib
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Item:
    def __init__(self, label='', info=None, art=None, **kwargs):
        self.label, self.info, self.art = label, info or {}, art or {}
        self.path = ''
        self.context = []
        self.playable = False


def route(func, **kwargs):
    return 'plugin://slyguy.max.cleanui/?' + urlencode({'_': func.__name__, **kwargs})


userdata = {'profile': {'id': 'one'}}
xbmc = types.ModuleType('xbmc')
xbmc.LOGWARNING, xbmc.LOGERROR, xbmc.LOGINFO, xbmc.LOGDEBUG = range(4)
xbmc.log = lambda *a: None
xbmc.sleep = lambda *a: None
xbmc.executebuiltin = lambda *a: None
sys.modules['xbmc'] = xbmc
gui = types.ModuleType('xbmcgui')
gui.WindowXMLDialog = type('WindowXMLDialog', (), {})
gui.WindowDialog = type('WindowDialog', (), {})
gui.Dialog = lambda: types.SimpleNamespace(ok=lambda *a: None)
sys.modules['xbmcgui'] = gui
addon = types.ModuleType('xbmcaddon')
addon.Addon = lambda: types.SimpleNamespace(getAddonInfo=lambda key: str(ROOT))
sys.modules['xbmcaddon'] = addon
slyguy = types.ModuleType('slyguy')
slyguy.userdata = userdata
slyguy.mem_cache = types.SimpleNamespace(empty=lambda: None, cached=lambda *a, **k: lambda f: f)
slyguy.gui = types.SimpleNamespace(busy=contextlib.nullcontext)
sys.modules['slyguy'] = slyguy

core = types.ModuleType('resources.lib.plugin')
core.plugin = types.SimpleNamespace(Item=Item, url_for=route)
core.api = None
core.re = re
core.log = types.SimpleNamespace(warning=lambda *a: None)
core.settings = types.SimpleNamespace(SYNC_WATCHLIST=types.SimpleNamespace(value=False))
for name in ('play', 'series', 'collection', 'clean_ui_movie', 'clean_ui_show', 'clean_ui_season'):
    exec('def ' + name + '(**kwargs): pass', core.__dict__)
source = ast.parse((ROOT / 'resources/lib/plugin.py').read_text(encoding='utf-8'))
for node in source.body:
    if isinstance(node, ast.FunctionDef) and node.name in ('_process_item', '_art', '_find_collection'):
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<core>', 'exec'), core.__dict__)
core.parse_row, core.get_art = core._process_item, core._art
sys.modules['resources.lib.plugin'] = core

from resources.lib.ui.repository import Repository
from resources.lib.ui.models import Card, Rail, Screen
from resources.lib.ui.controller import UIController
from resources.lib.ui.home_window import HomeWindow
from resources.lib.ui.detail_window import DetailWindow
from resources.lib.ui import constants as C


def movie(id='m', title='Movie'):
    return {'show': {'id': id, 'title': title, 'showType': 'MOVIE', 'images': []}}


class API:
    def __init__(self):
        self.calls = []

    def collection(self, id, page=1):
        self.calls.append(('collection', id, page))
        if id == 'web-menu-bar':
            return {'items': [{'collection': {'name': name, 'items': [
                {'link': {'linkedContentRoutes': [{'url': '/' + name}]}}]}}
                for name in ('home', 'movies', 'series')]}
        return {'items': [movie(str(page))],
                'meta': {'itemsCurrentPage': page, 'itemsTotalPages': 2}}

    def route(self, name):
        self.calls.append(('route', name))
        return {'items': [{'collection': {'id': str(i), 'title': 'Category',
                                         'items': [movie(str(i))]}} for i in range(24)]}

    def search(self, query, page):
        return self.collection('search', page)

    def series(self, id):
        return {'id': id, 'name': 'Series', 'showType': 'SERIES', 'images': [], 'seasons': []}

    def season(self, id, number, page=1):
        # Missing edit must remain a navigable show, not a non-playable episode.
        return {'items': [{'video': {'id': 'episode', 'name': 'Episode',
                'videoType': 'EPISODE', 'show': {'id': 'show'}}}],
                'meta': {'itemsCurrentPage': page, 'itemsTotalPages': 2}}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        userdata.clear()
        userdata['profile'] = {'id': 'one'}
        self.api = API()
        self.repo = Repository(self.api)

    def test_title_without_name_and_parser_does_not_mutate_response(self):
        row = movie()
        before = copy.deepcopy(row)
        card = self.repo._card_from_raw(row)
        self.assertEqual(card.label, 'Movie')
        self.assertEqual(row, before)
        self.assertIn('m', card.play_path)

    def test_one_malformed_item_does_not_discard_rail(self):
        cards = self.repo._cards_from_rows([None, {'video': {'name': 'Broken', 'videoType': 'EPISODE'}}, movie()])
        self.assertEqual(len(cards), 1)

    def test_home_is_bounded_and_all_categories_reachable(self):
        screen = self.repo.build_home()
        ids = []
        for _ in range(10):
            self.assertLessEqual(len(screen.rails), C.MAX_RAILS_HOME)
            ids.extend(rail.rail_id for rail in screen.rails if rail.rail_id)
            last = screen.rails[-1].items[-1]
            if last.kind != 'page' or last.source_item[0] != 'route_page':
                break
            screen = self.repo.build_next(last)
        self.assertEqual(ids, [str(i) for i in range(24)])

    def test_warm_cache_does_not_refetch_and_models_are_independent(self):
        first = self.repo.build_home()
        calls = len(self.api.calls)
        first.rails[0].items.clear()
        second = self.repo.build_home()
        self.assertTrue(second.rails[0].items)
        self.assertEqual(len(self.api.calls), calls)

    def test_profile_switch_invalidates_cache_and_movie_metadata(self):
        self.repo.build_home()
        self.assertTrue(self.repo._raw_items)
        userdata['profile'] = {'id': 'two'}
        self.repo._check_profile()
        self.assertFalse(self.repo._raw_items)
        self.assertFalse(self.repo._cache)

    def test_movies_uses_dedicated_route_not_every_menu_route(self):
        self.repo.build_movies_home()
        self.assertEqual([c for c in self.api.calls if c[0] == 'route'], [('route', 'movies')])

    def test_collection_pagination(self):
        first = self.repo.build_collection('c', 'Collection')
        second = self.repo.build_next(first.rails[0].items[-1])
        self.assertEqual(second.rails[0].items[0].deeplink_id, '2')
        self.assertNotEqual(second.rails[0].items[-1].kind, 'page')

    def test_search_pagination(self):
        screen = self.repo.build_search('Movie')
        self.assertEqual(self.repo.build_next(screen.rails[0].items[-1]).rails[0].items[0].deeplink_id, '2')

    def test_missing_episode_edit_retains_show_navigation(self):
        screen = self.repo.build_season_detail('show', 1)
        self.assertEqual(screen.rails[0].items[0].kind, Card.SHOW)
        self.assertEqual(screen.rails[0].items[-1].kind, 'page')

    def test_image_sizes_and_signed_urls(self):
        art = self.repo._normalize_art({'poster': 'https://image.test/a?w=600',
                                       'fanart': 'https://image.test/b?token=secret'})
        self.assertEqual(art['poster'], 'https://image.test/a?w=600')
        self.assertEqual(art['fanart'], 'https://image.test/b?token=secret')

    def test_artwork_uses_raw_query_without_appending_second_question_mark(self):
        from resources.lib.ui.artwork import artwork_from_images
        source = 'https://image.test/poster.jpg?host=images.test&crop=2%3A3&sig=abc%2Bdef'
        row = movie()
        row['show']['images'] = [{'kind': 'poster-with-logo', 'src': source}]
        self.assertEqual(self.repo._card_from_raw(row).art['poster'], source)
        self.assertEqual(artwork_from_images(row['show']['images'])['poster'], source)

    def test_plain_artwork_retains_original_slyguy_thumbnail_width(self):
        row = movie()
        row['show']['images'] = [{'kind': 'poster-with-logo', 'src': 'https://image.test/cover.jpg'}]
        self.assertEqual(self.repo._card_from_raw(row).art['poster'], 'https://image.test/cover.jpg?w=600')

    def test_episode_inherits_unmodified_parent_logo_query(self):
        logo = 'https://image.test/logo.png?host=cdn&sig=signed'
        row = {'video': {'id': 'episode', 'name': 'Episode', 'videoType': 'EPISODE',
               'edit': {'id': 'edit', 'duration': 1000},
               'images': [{'kind': 'default', 'src': 'https://image.test/episode.jpg'}],
               'show': {'id': 'show', 'name': 'Show',
                        'images': [{'kind': 'logo-left', 'src': logo}]}}}
        self.assertEqual(self.repo._card_from_raw(row).art['clearlogo'], logo)

    def test_seasons_without_optional_counts_are_navigable(self):
        data = self.api.series('show')
        data['seasons'] = [{'seasonNumber': '2'}, {'seasonNumber': 1},
                           {'seasonNumber': 3, 'videoCountByType': {'EPISODE': 0}}]
        self.api.series = lambda unused: data
        screen = self.repo.build_show_detail('show')
        self.assertEqual([card.season_id for card in screen.rails[0].items], ['1', '2'])

    def test_episode_with_parent_title_but_no_name_is_not_dropped(self):
        row = {'video': {'id': 'episode', 'name': 'Episode', 'videoType': 'EPISODE',
               'edit': {'id': 'edit', 'duration': 1000},
               'show': {'id': 'show', 'title': 'Parent title', 'images': []}}}
        cards = self.repo._cards_from_rows([row])
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].info['tvshowtitle'], 'Parent title')
        self.assertNotIn('name', row['video']['show'])

    def test_home_does_not_fetch_all_unloaded_collections(self):
        self.api.route = lambda name: {'items': [{'collection': {'id': str(i)}} for i in range(12)]}
        first = self.repo.build_home()
        calls = [c for c in self.api.calls if c[0] == 'collection' and c[1] != 'web-menu-bar']
        self.assertEqual(len(calls), 2)
        self.assertEqual(first.rails[-1].items[0].source_item[1][1], 2)
        second = self.repo.build_next(first.rails[-1].items[0])
        self.assertEqual(second.rails[0].rail_id, '2')

    def test_cached_screens_share_readonly_source_but_not_selection_state(self):
        first = self.repo.build_home()
        second = self.repo.build_home()
        self.assertIs(first.rails[0].items[0].source_item, second.rails[0].items[0].source_item)
        self.assertIsNot(first.rails[0].items, second.rails[0].items)
        self.assertIsNot(first.rails[0].items[0].art, second.rails[0].items[0].art)

    def test_cache_and_raw_metadata_are_bounded(self):
        for i in range(520):
            self.repo._card_from_raw(movie(str(i)))
        self.assertLessEqual(len(self.repo._raw_items), 500)
        for i in range(20):
            self.repo.build_collection(str(i), 'Collection')
        self.assertLessEqual(len(self.repo._cache), 12)

    def test_post_playback_contract(self):
        self.assertFalse(self.repo.refresh_continue_watching(Screen(Screen.HOME)))


class NavigationTests(unittest.TestCase):
    def test_restored_detail_releases_curtain_with_multiple_parent_screens(self):
        controller = UIController()
        closed = []
        window = object()
        controller._processing_playback = True
        controller._restored_stack = [Screen(Screen.HOME), Screen(Screen.SHOW), Screen(Screen.SEASON)]
        controller._transition_curtain = types.SimpleNamespace(close=lambda: closed.append(True))
        controller._transition_release_target = window
        controller.notify_window_focused(window)
        self.assertEqual(closed, [True])

    def test_max_profile_change_is_detected(self):
        userdata.clear()
        userdata['profile'] = {'id': 'one'}
        core.api = API()
        controller = UIController()
        core._select_profile = lambda: userdata.update(profile={'id': 'two'})
        seen = []
        window = types.SimpleNamespace(replace_screen=lambda screen, kind: seen.append(kind) or True)
        with patch('resources.lib.ui.profile_window.choose_profile',
                   side_effect=lambda path: userdata.update(profile={'id': 'two'}) or True):
            self.assertTrue(controller.select_profile(window))
        self.assertEqual(seen, ['home'])

    def test_kids_lockdown_blocks_selector(self):
        userdata['kid_lockdown'] = True
        core._select_profile = lambda: self.fail('Selector must not open')
        self.assertFalse(UIController().select_profile())
        userdata.pop('kid_lockdown')

    def test_home_rail_ids_are_consistent_for_all_screens(self):
        window = object.__new__(HomeWindow)
        for kind in ('home', 'movies', 'series'):
            window.screen_kind = kind
            self.assertEqual([window._rail_control_id(i) for i in range(8)], list(range(4000, 4008)))

    def test_detail_back_restores_previous_page(self):
        window = object.__new__(DetailWindow)
        previous = Screen(Screen.SEARCH, title='First')
        window._page_history = [previous]
        window.onInit = lambda: None
        window._close_current_window()
        self.assertIs(window.screen, previous)


class LayoutTests(unittest.TestCase):
    def test_all_navigation_targets_exist_and_ids_unique(self):
        for path in ROOT.glob('resources/skins/Default/1080i/*.xml'):
            root = ET.parse(path).getroot()
            ids = [node.get('id') for node in root.findall('.//control[@id]')]
            self.assertEqual(len(ids), len(set(ids)), path.name)
            for tag in ('onup', 'ondown', 'onleft', 'onright', 'defaultcontrol'):
                for node in root.findall('.//' + tag):
                    if (node.text or '').isdigit() and node.text != '0':
                        self.assertIn(node.text, ids, (path.name, tag, node.text))

    def test_home_has_exactly_eight_lists(self):
        root = ET.parse(ROOT / 'resources/skins/Default/1080i/uihome.xml')
        self.assertEqual(len(root.findall('.//control[@type="fixedlist"]')), 8)

    def test_all_python_compiles(self):
        for path in ROOT.rglob('*.py'):
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')


if __name__ == '__main__':
    unittest.main()
