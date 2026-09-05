import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import test_cleanui as f
from resources.lib.ui import profile_window
from test_detail_layout import window


class TVRedesignTests(unittest.TestCase):
    def test_menu_destinations_are_service_backed_and_hidden_entries_excluded(self):
        api=f.API()
        def entry(name,url,hidden=False):
            return {'hidden':hidden,'collection':{'title':name,'items':[
                {'link':{'linkedContentRoutes':[{'url':url}]}}]}}
        api.collection=lambda *a,**k:{'items':[entry('HBO','/channel/real-id'),
            entry('Niños y Familia','/genre/family'),entry('HBO','/wrong',True)]}
        repo=f.Repository(api)
        self.assertEqual(repo.navigation_targets(),{'hbo':'channel/real-id','kids':'genre/family'})
        with self.assertRaises(ValueError): repo.build_navigation_section('invented')

    def test_series_screen_has_selected_season_episodes_and_functional_play(self):
        api=f.API()
        api.series=lambda unused:{'id':'show','name':'Series','showType':'SERIES','images':[],
                                  'seasons':[{'seasonNumber':1},{'seasonNumber':2}]}
        def season(show,number,page=1):
            return {'items':[{'video':{'id':'episode','name':'Episode','videoType':'EPISODE',
                'episodeNumber':7,'seasonNumber':number,'images':[],
                'edit':{'id':'edit','duration':1000},'show':{'id':'show','name':'Series','images':[]}}}],
                'meta':{'itemsCurrentPage':page,'itemsTotalPages':2}}
        api.season=season
        repo=f.Repository(api)
        screen=repo.build_show_episodes('show','2')
        self.assertEqual(screen.selected_season.season_id,'2')
        self.assertEqual(screen.play_label,'Ver T2 E7')
        self.assertIn('edit',screen.hero.play_path)
        self.assertEqual(len(screen.season_choices),2)
        next_screen=repo.build_next(screen.rails[0].items[-1])
        self.assertEqual(next_screen.selected_season.season_id,'2')
        self.assertEqual(next_screen.screen_type,f.Screen.SHOW)

    def test_season_selector_is_reachable_and_has_down_path_to_episodes(self):
        detail=window(f.C.SCREEN_SHOW,rails=(0,),actions=('season_label',))
        detail._configure_navigation()
        self.assertTrue(detail.controls[1004].isVisible())
        self.assertEqual(detail.controls[1003].navigation['right'],1004)
        self.assertEqual(detail.controls[1004].navigation['down'],4000)
        self.assertEqual(detail.controls[4000].navigation['up'],1004)

    def test_profile_cancel_does_not_switch_account(self):
        f.userdata.clear()
        f.userdata['profile']={'id':'one'}
        api=types.SimpleNamespace(profiles=lambda:[{'id':'one','profileName':'One'}])
        with patch.object(f.core,'api',api),patch.object(f.core,'_set_profile',create=True) as switch, \
             patch.object(profile_window,'ProfileWindow') as cls:
            cls.return_value.selected=None
            self.assertFalse(profile_window.choose_profile('addon-path'))
            switch.assert_not_called()

    def test_profile_switch_delegates_pin_and_auth_to_unchanged_core(self):
        f.userdata.clear()
        f.userdata['profile']={'id':'one'}
        selected={'id':'two','profileName':'Two','pinRestricted':True}
        api=types.SimpleNamespace(profiles=lambda:[selected])
        with patch.object(f.core,'api',api),patch.object(f.core,'_set_profile',create=True) as switch, \
             patch.object(profile_window,'ProfileWindow') as cls:
            cls.return_value.selected=selected
            self.assertTrue(profile_window.choose_profile('addon-path'))
            switch.assert_called_once_with(selected,switching=True)

    def test_empty_series_does_not_fake_play_or_season_action(self):
        screen=f.Repository(f.API()).build_show_episodes('show')
        self.assertEqual(screen.season_choices,[])
        self.assertFalse(screen.hero.play_path)

    def test_detail_rail_fits_screen_and_buttons_do_not_overlap_it(self):
        root=ET.parse(f.ROOT/'resources/skins/Default/1080i/ui_detail.xml')
        group=root.find('.//control[@id="5000"]')
        top=int(group.findtext('top'))
        self.assertLessEqual(top+int(group.findtext('height')),1080)
        self.assertGreaterEqual(int(group.findtext('height')),368)
        for cid in (1000,1001,1002,1003,1004):
            button=root.find('.//control[@id="%s"]'%cid)
            self.assertLessEqual(int(button.findtext('top'))+int(button.findtext('height')),top)

    def test_profiles_use_circle_mask_and_no_fake_account_editor(self):
        root=ET.parse(f.ROOT/'resources/skins/Default/1080i/ui_profiles.xml')
        self.assertTrue(root.findall('.//texture[@diffuse="circle-mask.png"]'))
        text=ET.tostring(root.getroot(),encoding='unicode')
        self.assertNotIn('Nuevo perfil',text)
        self.assertNotIn('Editar',text)
