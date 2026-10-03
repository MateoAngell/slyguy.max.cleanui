"""Observe Kodi playback without changing its windows or media pipeline."""
import threading
import time

import xbmc


def observe_playback(path, on_started=None, cancelled=None):
    """Keep navigation suspended until Kodi reports a terminal player event.

    A false isPlaying sample is not an end event: buffering and decoder
    transitions can produce it. Callbacks own the active playback lifetime.
    The finite timeout applies only before playback starts.
    """
    class Observer(xbmc.Player):
        def __init__(self):
            super(Observer, self).__init__()
            self.started = threading.Event()
            self.finished = threading.Event()
            self.failed = False

        def onPlayBackStarted(self):
            self.started.set()

        def onAVStarted(self):
            self.started.set()

        def onPlayBackStopped(self):
            self.finished.set()

        def onPlayBackEnded(self):
            self.finished.set()

        def onPlayBackError(self):
            self.failed = True
            self.finished.set()

    player = Observer()
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + 60.0
    prompt_seen = False
    quiet_since = None
    dialogs = ('busydialog', 'busydialognocancel', 'selectdialog',
               'contextmenu', 'yesnodialog', 'okdialog', 'progressdialog')
    xbmc.executebuiltin('PlayMedia("{}",0)'.format(path.replace('"', '\\"')), False)
    try:
        while not player.started.is_set():
            if monitor.abortRequested() or (cancelled and cancelled()):
                return False
            if player.finished.is_set():
                return False
            # Covers a callback arriving before the observer is registered.
            if player.isPlaying():
                player.started.set()
                break
            active = any(xbmc.getCondVisibility('Window.IsVisible({})'.format(name))
                         for name in dialogs)
            now = time.monotonic()
            prompt_seen = prompt_seen or active
            quiet_since = None if active else (quiet_since or now)
            if prompt_seen and quiet_since and now - quiet_since >= 1.0:
                return False
            if now >= deadline and not active:
                return False
            xbmc.sleep(100)
        if monitor.abortRequested() or (cancelled and cancelled()):
            return False
        if on_started:
            on_started()
        # No player polling, catalogue requests or GUI writes during video.
        while not player.finished.is_set():
            # Kodi's native wait also dispatches pending Python player
            # callbacks. threading.Event.wait alone can starve that dispatch.
            if monitor.waitForAbort(0.5) or (cancelled and cancelled()):
                return False
        return not player.failed
    finally:
        # Dropping the observer unregisters its callbacks with Kodi. Do not
        # keep it on the controller or reuse it for a later request.
        del player
