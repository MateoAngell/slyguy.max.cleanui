"""Only owned root favourites may change; Kodi persists them, backup first."""
import ast
import copy
import json
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class FavouriteTests(unittest.TestCase):
    def run_case(self, folder, favourites, copy_ok=True, remove_error=False):
        tree = ast.parse((ROOT/folder/'resources/lib/ui/entry.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'repair_root_favourite')
        current, events = copy.deepcopy(favourites), []
        def rpc(raw):
            request = json.loads(raw)
            method, params = request['method'], request['params']
            if method == 'Favourites.GetFavourites':
                return json.dumps(dict(result=dict(favourites=current)))
            events.append(('toggle', copy.deepcopy(params)))
            if remove_error and params['type'] == 'window':
                return json.dumps(dict(error=dict(code=-1)))
            matching = next((f for f in current if f.get('type') == params['type'] and
                f.get('path', f.get('windowparameter')) == params.get('path', params.get('windowparameter'))), None)
            if matching:
                current.remove(matching)
            else:
                current.append(params)
            return json.dumps(dict(result='OK'))
        vfs = types.SimpleNamespace(mkdirs=lambda path: True,
            copy=lambda source, target: events.append(('backup', source, target)) or copy_ok)
        addon = types.SimpleNamespace(getAddonInfo=lambda k: 'owned' if k == 'id' else 'special://profile/addon_data/owned/')
        ns = dict(json=json, uuid=uuid, xbmc=types.SimpleNamespace(
            executeJSONRPC=rpc, log=lambda *a: None, LOGINFO=1, LOGWARNING=2))
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<favourite>', 'exec'), ns)
        with patch.dict('sys.modules', xbmcvfs=vfs):
            result = ns['repair_root_favourite'](addon)
        return result, current, events

    def test_root_replaced_after_backup_other_routes_untouched(self):
        root = dict(title='My Disney', type='window', window='videos', windowparameter='plugin://owned/', thumbnail='avatar.png')
        other = dict(title='Episode', type='window', window='videos', windowparameter='plugin://owned/?play=123')
        for folder in ('.',):
            result, current, events = self.run_case(folder, [root, other])
            self.assertTrue(result)
            self.assertEqual(events[0][0], 'backup')
            self.assertEqual(current, [other, dict(title='My Disney', type='script', path='owned', thumbnail='avatar.png')])
            result, current, events = self.run_case(folder, current)
            self.assertFalse(result)
            self.assertEqual(events, [])

    def test_missing_backup_or_failed_removal_leaves_original(self):
        root = dict(title='Max', type='window', window='videos', windowparameter='plugin://owned/')
        for folder in ('.',):
            for args in (dict(copy_ok=False), dict(remove_error=True)):
                result, current, events = self.run_case(folder, [root], **args)
                self.assertFalse(result)
                self.assertEqual(current, [root])

    def test_ambiguous_external_and_existing_direct_are_unchanged(self):
        root = dict(title='Max', type='window', window='videos', windowparameter='plugin://owned/')
        cases = ([root, dict(root, windowparameter='plugin://owned')],
                 [dict(root, windowparameter='plugin://other/')],
                 [root, dict(title='Direct', type='script', path='owned')])
        for folder in ('.',):
            for favourites in cases:
                result, current, events = self.run_case(folder, favourites)
                self.assertFalse(result)
                self.assertEqual(current, favourites)
                self.assertEqual(events, [])


if __name__ == '__main__':
    unittest.main()
