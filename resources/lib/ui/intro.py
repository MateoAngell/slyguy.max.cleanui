"""Play the supplied local intro only while the first profiles are loading.

Kodi decodes it in its native video control; no Python worker, image cache,
minimum duration or catalogue prefetch is needed. The base survives the clip.
"""
import os

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
            self.startup.finish()


class Startup:
    def __init__(self, addon_path):
        self.cancelled = False
        self.ready = False
        self.player = None
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
            self.finish()
            xbmc.log('[CLEANUI] Intro unavailable; continuing without it', xbmc.LOGWARNING)

    def finish(self):
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
        self.finish()
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
        raise RuntimeError('Startup already owned')
    _active = Startup(addon_path)
    return _active


def finish():
    return _active.finish() if _active is not None else True


def loading():
    return _active is not None and not _active.ready
