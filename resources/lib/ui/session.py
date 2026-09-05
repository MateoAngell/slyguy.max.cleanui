"""Own a single visual session while Kodi dispatches playback routes."""
import xbmc
import xbmcgui
from slyguy import plugin

RUNNING = 'MaxCleanUI.Running'


def run(method, *args):
    from .controller import UIController
    owner = xbmcgui.Window(10000)
    folder = plugin.Folder(cacheToDisc=False)
    folder.add_item(label='HBO Max Clean UI', path='special://home', bookmark=False)
    if owner.getProperty(RUNNING) == 'true':
        return folder
    owner.setProperty(RUNNING, 'true')
    controller = None
    try:
        xbmc.executebuiltin('ActivateWindow(Home)')
        controller = UIController()
        getattr(controller, method)(*args)
    finally:
        owner.clearProperty(RUNNING)
        if controller:
            controller.end_transition()
    return folder
