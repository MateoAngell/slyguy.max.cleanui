"""Own one complete local intro and one discardable profile preparation."""
import os
import threading
import time

import xbmc
import xbmcgui

_active = None


def _same_file(left, right):
    return bool(left) and os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


class IntroPlayer(xbmc.Player):
    def __init__(self, path):
        super(IntroPlayer, self).__init__()
        self.path = path
        self.requested = False
        self.closed = False
        self.ended = False
        self.started = False

    def current_file(self):
        try:
            return self.getPlayingFile()
        except RuntimeError:
            return ''

    def start(self):
        if self.closed or self.isPlaying() or not os.path.isfile(self.path):
            return
        item = xbmcgui.ListItem(path=self.path, offscreen=True)
        item.setInfo('video', {'title': 'Intro', 'mediatype': 'video'})
        self.requested = True
        self.play(self.path, item, windowed=True)

    def finish(self):
        self.closed = True
        if not self.requested:
            return
        self.requested = False
        current = self.current_file()
        # A queued local open may not have a filename yet. Kodi's synchronous
        # stop follows the queued play; never stop another named media item.
        if not self.ended and (not current or _same_file(current, self.path)):
            self.stop()

    def onAVStarted(self):
        self.started = True
        # Guard a callback queued before cancellation, not a later film.
        if self.closed and _same_file(self.current_file(), self.path):
            self.stop()

    def onPlayBackEnded(self):
        self.ended = True

    def onPlayBackStopped(self):
        self.ended = True

    def onPlayBackError(self):
        self.ended = True


class IntroWindow(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        self.startup = kwargs.pop('startup')
        super(IntroWindow, self).__init__(*args, **kwargs)

    def onAction(self, action):
        if action.getId() in (9, 10, 92) and not self.startup.ready:
            self.startup.cancelled = True
            self.startup.abort()


class Startup:
    def __init__(self, addon_path):
        self.cancelled = False
        self.ready = False
        self.player = None
        self.worker = None
        self.window = IntroWindow('ui_intro.xml', addon_path, 'Default', '1080i', startup=self)
        self.window.show()
        try:
            if self.cancelled:
                return
            self.player = IntroPlayer(os.path.join(addon_path, 'resources', 'media', 'intro.mp4'))
            self.player.start()
            self.window.setProperty('cleanui.intro.visible', 'true' if self.player.requested else '')
        except Exception:
            # Optional presentation must never prevent the existing UI opening.
            self.abort()
            self.finish()
            xbmc.log('[CLEANUI] Intro unavailable; continuing without it', xbmc.LOGWARNING)

    def abort(self):
        if self.player:
            self.player.finish()
        if self.window:
            self.window.setProperty('cleanui.intro.visible', '')

    def load(self, prepare):
        """Only profile data runs off-thread; no worker touches GUI controls."""
        if self.ready:
            return prepare()
        if self.worker is not None:
            raise RuntimeError('Startup preparation already active')
        result = {}
        done = threading.Event()
        def run():
            try:
                value = prepare()
                if not self.cancelled:
                    result['value'] = value
            except Exception as error:
                if not self.cancelled:
                    result['error'] = error
            finally:
                done.set()
        self.worker = threading.Thread(target=run, name='CleanUIProfiles', daemon=True)
        self.worker.start()
        monitor = xbmc.Monitor()
        while not done.is_set():
            if self.cancelled or monitor.waitForAbort(0.05):
                self.cancelled = True
                self.abort()
                # Keep this service session owned until its sole API call ends.
                # No new launch can race an abandoned profile request.
                while not done.is_set() and not monitor.waitForAbort(0.1):
                    pass
                return None
        self.worker.join()
        self.worker = None
        if self.cancelled:
            return None
        if 'error' in result:
            raise result['error']
        return result.get('value')

    def finish(self):
        # Profile readiness does not stop the clip. Pump Kodi callbacks until
        # its natural end, cancellation or playback failure.
        monitor = xbmc.Monitor()
        deadline = time.monotonic() + 30.0
        while self.player and self.player.requested and not self.player.ended:
            if self.cancelled or monitor.waitForAbort(0.05):
                self.cancelled = True
                break
            if time.monotonic() >= deadline:
                xbmc.log('[CLEANUI] Intro failed to finish; continuing', xbmc.LOGWARNING)
                break
        self.ready = True
        try:
            self.window.setProperty('cleanui.intro.visible', '')
            if self.player:
                self.player.finish()
        except Exception:
            xbmc.log('[CLEANUI] Intro cleanup failed', xbmc.LOGWARNING)
        finally:
            # Unregister the observer, release the clip/decoder, keep only base.
            self.player = None
        return not self.cancelled

    def close(self):
        global _active
        if self.window is None:
            return
        self.abort()
        self.ready = True
        self.player = None
        try:
            self.window.close()
        except Exception:
            xbmc.log('[CLEANUI] Intro base cleanup failed', xbmc.LOGWARNING)
        finally:
            self.window.startup = None
            self.window = None
            if _active is self:
                _active = None


def start(addon_path):
    global _active
    if _active is not None:
        return _active
    _active = Startup(addon_path)
    return _active


def finish():
    return _active.finish() if _active is not None else True


def loading():
    return _active is not None and not _active.ready


def prepare_profiles(prepare):
    return _active.load(prepare) if loading() else prepare()
