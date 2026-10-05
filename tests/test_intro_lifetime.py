"""Complete intro lifetime, cancellation and profile preparation."""
import importlib.util
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class IntroTests(unittest.TestCase):
    def modules(self):
        for folder in ('.',):
            events = []
            class Player:
                current = ''
                def isPlaying(self): return bool(self.current)
                def getPlayingFile(self): return self.current
                def play(self, path, item, windowed=False):
                    self.current = path
                    events.append(('play', path, windowed))
                def stop(self):
                    events.append('stop'); self.current = ''
            class Window:
                def __init__(self, *args, **kwargs): self.props = {}
                def show(self): events.append('base')
                def close(self): events.append('close')
                def setProperty(self, k, v): self.props[k] = v
            class Item:
                def __init__(self, **kwargs): pass
                def setInfo(self, *args): pass
            hook = [lambda: None]
            class Monitor:
                def waitForAbort(self, duration):
                    hook[0](); time.sleep(0.001); return False
            xbmc = types.SimpleNamespace(Player=Player, Monitor=Monitor, log=lambda *a: None, LOGWARNING=1)
            gui = types.SimpleNamespace(WindowXML=Window, ListItem=Item)
            with patch.dict(sys.modules, xbmc=xbmc, xbmcgui=gui):
                path = ROOT/folder/'resources/lib/ui/intro.py'
                spec = importlib.util.spec_from_file_location('intro_test', path)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                yield module, ROOT/folder, events, hook

    def test_ready_profiles_wait_for_natural_end(self):
        for module, source, events, hook in self.modules():
            startup = module.start(str(source))
            self.assertEqual(events[0], 'base'); self.assertTrue(events[1][2])
            self.assertEqual(module.prepare_profiles(lambda: [1]), [1])
            self.assertNotIn('stop', events)
            def ended():
                self.assertNotIn('stop', events); startup.player.onPlayBackEnded()
            hook[0] = ended
            self.assertTrue(module.finish()); self.assertNotIn('stop', events)
            self.assertIsNone(startup.player); self.assertIsNone(startup.worker)
            self.assertFalse(module.loading()); startup.close(); startup.close()
            self.assertEqual(events.count('close'), 1); self.assertIsNone(module._active)

    def test_black_base_precedes_clip_and_start_is_idempotent(self):
        for module, source, events, hook in self.modules():
            startup = module.start(str(source))
            self.assertEqual(events[0], 'base')
            self.assertIs(module.start(str(source)), startup)
            self.assertEqual(sum(isinstance(e, tuple) for e in events), 1)
            startup.player.onPlayBackEnded(); startup.finish(); startup.close()

    def test_clip_ends_before_slow_profiles_base_survives(self):
        for module, source, events, hook in self.modules():
            startup = module.start(str(source)); released = threading.Event()
            def profiles(): released.wait(1); return ['profile']
            def ended(): startup.player.onPlayBackEnded(); released.set()
            hook[0] = ended
            self.assertEqual(module.prepare_profiles(profiles), ['profile'])
            self.assertNotIn('close', events); self.assertTrue(module.finish()); startup.close()

    def test_cancel_discards_late_profile_without_replay(self):
        for module, source, events, hook in self.modules():
            startup = module.start(str(source)); released = threading.Event()
            def profiles(): released.wait(1); return ['late']
            def cancelled():
                startup.window.onAction(types.SimpleNamespace(getId=lambda: 92)); released.set()
            hook[0] = cancelled
            self.assertIsNone(module.prepare_profiles(profiles)); self.assertFalse(module.finish())
            self.assertEqual(sum(isinstance(e, tuple) for e in events), 1)
            self.assertIn('stop', events); startup.close()

    def test_foreign_video_never_stopped(self):
        for module, source, events, hook in self.modules():
            startup = module.start(str(source)); startup.player.current = 'https://existing.example/video'
            startup.close(); self.assertNotIn('stop', events)

    def test_missing_intro_and_error_recover(self):
        for module, source, events, hook in self.modules():
            with patch.object(module.os.path, 'isfile', return_value=False): startup = module.start(str(source))
            self.assertTrue(module.finish()); startup.close(); startup = module.start(str(source))
            startup.player.onPlayBackError(); self.assertTrue(module.finish()); startup.close()

    def test_worker_error_reaches_owner(self):
        for module, source, events, hook in self.modules():
            startup = module.start(str(source)); main = threading.get_ident()
            def fails():
                self.assertNotEqual(threading.get_ident(), main); raise ValueError('profiles unavailable')
            with self.assertRaisesRegex(ValueError, 'profiles unavailable'): module.prepare_profiles(fails)
            self.assertIsNone(startup.worker); startup.close()


if __name__ == '__main__': unittest.main()
