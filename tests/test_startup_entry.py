import importlib.util
import ast
import json
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parent.parent


class EntryTests(unittest.TestCase):
    def test_direct_launch_claims_once_and_cancel_releases_owner(self):
        for folder in ('.',):
            props, events = {}, []
            owner = types.SimpleNamespace(getProperty=lambda k: props.get(k, ''),
                setProperty=lambda k,v: props.update({k:v}), clearProperty=lambda k: props.pop(k, None))
            addon = types.SimpleNamespace(getAddonInfo=lambda k: 'addon')
            intro = types.ModuleType('startup_case.intro')
            intro.start = lambda path: events.append('intro') or types.SimpleNamespace(
                cancelled=True, close=lambda: events.append('closed'))
            package = types.ModuleType('startup_case'); package.__path__=[]; package.intro=intro
            core = types.ModuleType('resources.lib.plugin')
            core.before_dispatch = lambda: events.append('prepare')
            core.api = types.SimpleNamespace(logged_in=True)
            resources = types.ModuleType('resources'); lib = types.ModuleType('resources.lib')
            resources.lib=lib; lib.plugin=core
            tree=ast.parse((ROOT/folder/'resources/lib/ui/entry.py').read_text())
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='launch_root')
            ns=dict(__package__='startup_case', json=json, unquote=unquote, uuid=uuid,
                xbmcaddon=types.SimpleNamespace(Addon=lambda:addon), xbmcgui=types.SimpleNamespace(Window=lambda _:owner),
                capture_origin=lambda: {}, repair_root_favourite=lambda addon: None,
                restore_origin=lambda value: events.append('restored'))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<entry>','exec'),ns)
            modules={'startup_case':package,'startup_case.intro':intro,
                'resources':resources,'resources.lib':lib,'resources.lib.plugin':core}
            with patch.dict(sys.modules, modules):
                for key in ('addon.LaunchOwner','MaxCleanUI.Running','DisneyPlusCleanUI.Running'):
                    props[key]='active'
                    ns['launch_root']()
                    self.assertEqual(events, [], 'A second launch must not open an intro')
                    props.clear()
                ns['launch_root']()
                self.assertEqual(events, ['intro','prepare','closed','restored'])
                self.assertEqual(props, {})
                events.clear()
                ns['launch_root']()  # cancellation must permit reopening
                self.assertEqual(events, ['intro','prepare','closed','restored'])

    def test_intro_import_error_releases_direct_launch(self):
        for folder in ('.',):
            props, events = {}, []
            owner=types.SimpleNamespace(getProperty=lambda k:props.get(k,''),
                setProperty=lambda k,v:props.update({k:v}),clearProperty=lambda k:props.pop(k,None))
            addon=types.SimpleNamespace(getAddonInfo=lambda k:'addon')
            package=types.ModuleType('missing_intro_case');package.__path__=[]
            tree=ast.parse((ROOT/folder/'resources/lib/ui/entry.py').read_text())
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='launch_root')
            ns=dict(__package__='missing_intro_case',json=json,unquote=unquote,uuid=uuid,
                xbmcaddon=types.SimpleNamespace(Addon=lambda:addon),xbmcgui=types.SimpleNamespace(Window=lambda _:owner),
                capture_origin=lambda:{},restore_origin=lambda value:events.append('restored'))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<entry>','exec'),ns)
            with patch.dict(sys.modules,{'missing_intro_case':package,'missing_intro_case.intro':None}):
                with self.assertRaises(ImportError): ns['launch_root']()
            self.assertEqual(events,['restored']);self.assertEqual(props,{})

    def test_launch_exception_restores_and_releases_only_owner(self):
        for folder in ('.',):
            events=[]
            props={'addon.LaunchOwner':'owner'}
            owner=types.SimpleNamespace(getProperty=lambda k:props.get(k,''),clearProperty=lambda k:props.pop(k,None))
            addon=types.SimpleNamespace(getAddonInfo=lambda key:'addon')
            intro=types.ModuleType('startup_case.intro')
            intro.start=lambda path:events.append('play') or types.SimpleNamespace(close=lambda:events.append('closed'))
            package=types.ModuleType('startup_case');package.__path__=[];package.intro=intro
            resources=types.ModuleType('resources');lib=types.ModuleType('resources.lib')
            core=types.ModuleType('resources.lib.plugin');core.before_dispatch=lambda:(_ for _ in ()).throw(RuntimeError('init failed'))
            resources.lib=lib;lib.plugin=core
            tree=ast.parse((ROOT/folder/'resources/lib/ui/entry.py').read_text())
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='launch_root')
            ns=dict(__package__='startup_case',json=json,unquote=unquote,
                xbmcaddon=types.SimpleNamespace(Addon=lambda:addon),xbmcgui=types.SimpleNamespace(Window=lambda _:owner),
                repair_root_favourite=lambda addon:None,
                restore_origin=lambda value:events.append('restored'))
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'<entry>','exec'),ns)
            with patch.dict(sys.modules,{'startup_case':package,'startup_case.intro':intro,
                'resources':resources,'resources.lib':lib,'resources.lib.plugin':core}):
                with self.assertRaisesRegex(RuntimeError,'init failed'):
                    ns['launch_root'](quote(json.dumps(dict(token='owner',origin={})),safe=''))
            self.assertEqual(events,['play','closed','restored']);self.assertNotIn('addon.LaunchOwner',props)

    def test_resolve_precedes_launch_and_restore_uses_origin(self):
        for folder in ('.',):
            events, props = [], {}
            window = types.SimpleNamespace(getFocusId=lambda: 50,
                getProperty=lambda k: props.get(k, ''), setProperty=lambda k,v: props.update({k:v}),
                clearProperty=lambda k: props.pop(k, None))
            current = [1100]
            xbmc = types.SimpleNamespace(getInfoLabel=lambda k: '', getCondVisibility=lambda k: False,
                executebuiltin=lambda cmd, wait=False: events.append(cmd), log=lambda *a: None, LOGINFO=1)
            gui = types.SimpleNamespace(Window=lambda i: window, getCurrentWindowId=lambda: current[0])
            addon = types.SimpleNamespace(Addon=lambda: types.SimpleNamespace(getAddonInfo=lambda k: 'slyguy.max.cleanui'))
            plugin = types.SimpleNamespace(endOfDirectory=lambda *a, **k: events.append('resolved'))
            with patch.dict(sys.modules, xbmc=xbmc, xbmcgui=gui, xbmcaddon=addon, xbmcplugin=plugin):
                spec=importlib.util.spec_from_file_location('entry',ROOT/folder/'resources/lib/ui/entry.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                with patch.object(sys,'argv',['plugin://slyguy.max.cleanui/','1','']):
                    with patch.object(module,'launch_root',side_effect=lambda **kw:events.append('inline')):
                        self.assertTrue(module.intercept_root())
                    self.assertEqual(events,['resolved','inline'])
                    self.assertFalse(any(e.startswith('RunScript') for e in events))
                current[0]=10025
                module.restore_origin(dict(window=10134,path='',focus=0))
                self.assertEqual(events[-1],'ReplaceWindow(10134)')
                module.restore_origin(dict(window=10025,path='plugin://slyguy.max.cleanui/'))
                self.assertEqual(events[-1],'Action(PreviousMenu)')
                with patch.object(sys,'argv',['plugin://slyguy.max.cleanui/','1','?play=media']):
                    self.assertFalse(module.intercept_root())


if __name__=='__main__':unittest.main()
