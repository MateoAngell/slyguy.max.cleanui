"""Layout, selection and motion preservation without claiming a Kodi render."""
import ast
import importlib.util
import sys
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

class PresentationTests(unittest.TestCase):

    def test_settings_use_slyguy_categories_without_leaving_clean_ui(self):
        for folder in ('.',):
            path = ROOT / folder / 'resources/lib/ui/home_window.py'
            tree = ast.parse(path.read_text(encoding='utf-8'))
            cls = next((n for n in tree.body if isinstance(n, ast.ClassDef)))
            method = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_open_settings'))
            selected = []
            setting = types.SimpleNamespace(label='Existing option', on_select=lambda: selected.append('option'))
            child = types.SimpleNamespace(label='Add-on', categories=[], settings=[setting])
            root = types.SimpleNamespace(label='Settings', categories=[child], settings=[])
            choices = iter((0, 0, -1, -1))
            shown = []
            dialog = types.SimpleNamespace(select=lambda title, labels: shown.append((title, labels)) or next(choices))
            types_module = types.ModuleType('slyguy.settings.types')
            types_module.Category = types.SimpleNamespace(get=lambda cid: root)
            sys.modules['slyguy.settings.types'] = types_module
            ns = {'xbmcgui': types.SimpleNamespace(Dialog=lambda: dialog)}
            exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), ns)
            ns['_open_settings'](types.SimpleNamespace())
            self.assertEqual(selected, ['option'])
            self.assertEqual([title for title, labels in shown], ['Settings', 'Add-on', 'Add-on', 'Settings'])
            self.assertNotIn('Addon.OpenSettings', path.read_text(encoding='utf-8'))

    def test_animations_are_finite_optional_and_do_not_touch_player(self):
        values = {}
        userdata = types.SimpleNamespace(get=lambda k, d=False: values.get(k, d), set=lambda k, v: values.__setitem__(k, v))
        for folder in ('.',):
            video = [False]
            sys.modules['xbmc'] = types.SimpleNamespace(getCondVisibility=lambda c: video[0])
            sys.modules['slyguy'] = types.SimpleNamespace(userdata=userdata)
            path = ROOT / folder / 'resources/lib/ui/effects.py'
            spec = importlib.util.spec_from_file_location('motion', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            calls = []
            control = types.SimpleNamespace(setAnimations=lambda a: calls.append(a))
            win = types.SimpleNamespace(getControl=lambda i: control, setProperty=lambda *a: None)
            values.clear()
            module.animate(win, (2002, 2003))
            self.assertEqual(len(calls), 2)
            for animations in calls:
                self.assertEqual(len(animations), 2)
                self.assertTrue(all(('time=150' in a[1] and 'loop' not in a[1] for a in animations)))
            module.toggle(win)
            module.animate(win, (2002,))
            self.assertEqual(len(calls), 2)
            module.toggle(win)
            video[0] = True
            module.animate(win, (2002,))
            self.assertEqual(len(calls), 2)

    def test_backgrounds_are_not_animated(self):
        for folder in ('.',):
            for file in (ROOT / folder / 'resources/skins/Default/1080i').glob('*.xml'):
                xml = ET.parse(file)
                first = xml.find('./controls/control')
                if first is not None:
                    self.assertFalse(first.findall('animation'), str(file))
                for a in xml.findall('.//animation'):
                    self.assertLessEqual(int(a.get('time', '0')), 180)
                    self.assertNotEqual(a.get('loop'), 'true')
if __name__ == '__main__':
    unittest.main()
