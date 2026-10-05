"""Lightweight root launcher: no service imports while Kodi opens a directory."""
import json
import sys
import uuid
from urllib.parse import quote, unquote

import xbmc
import xbmcaddon
import xbmcgui


def capture_origin():
    window = xbmcgui.getCurrentWindowId()
    host = xbmcgui.Window(window)
    try:
        focus = host.getFocusId()
    except Exception:
        focus = 0
    path = xbmc.getInfoLabel('Container.FolderPath')
    if window == 10025:
        for previous in (10000, 1100, 10134, 10040):
            if xbmc.getCondVisibility('Window.Previous({})'.format(previous)):
                return dict(window=previous, path='', focus=0, position='')
    # Kodi can move into Videos before invoking a plugin. In that case its
    # own window history, not a guessed skin-specific destination, owns Back.
    return dict(window=window, path=path, focus=focus,
                position=xbmc.getInfoLabel('Container.CurrentItem'))


def restore_origin(origin):
    window = int(origin.get('window') or 10000)
    path = origin.get('path') or ''
    addon = xbmcaddon.Addon().getAddonInfo('id')
    if window == 10025 and (not path or path.startswith('plugin://' + addon)):
        xbmc.executebuiltin('Action(PreviousMenu)', True)
        return
    target = str(window)
    if path and window in (10001, 10002, 10003, 10025, 10501, 10502):
        target += ',"{}"'.format(path.replace('"', '\\"'))
    if xbmcgui.getCurrentWindowId() != window or (path and xbmc.getInfoLabel('Container.FolderPath') != path):
        xbmc.executebuiltin('ReplaceWindow({})'.format(target), True)
    try:
        host = xbmcgui.Window(window)
        focus = int(origin.get('focus') or 0)
        if focus:
            host.setFocusId(focus)
        position = int(origin.get('position') or 0)
        if focus and position > 0:
            host.getControl(focus).selectItem(position - 1)
    except (RuntimeError, ValueError, AttributeError):
        pass


def intercept_root():
    import xbmcplugin
    if len(sys.argv) < 3 or sys.argv[2].strip('?') or sys.argv[0].rstrip('/').count('/') != 2:
        return False
    addon = xbmcaddon.Addon().getAddonInfo('id')
    owner = xbmcgui.Window(10000)
    key = addon + '.LaunchOwner'
    origin = capture_origin()
    # Complete the native request before RunScript: no empty plugin folder.
    xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False, cacheToDisc=False)
    if (owner.getProperty(key) or owner.getProperty('MaxCleanUI.Running')
            or owner.getProperty('DisneyPlusCleanUI.Running')):
        return True
    token = uuid.uuid4().hex
    owner.setProperty(key, token)
    payload = quote(json.dumps(dict(token=token, origin=origin)), safe='')
    xbmc.log('[CLEANUI][ENTRY] launch window={} focus={}'.format(origin['window'], origin['focus']), xbmc.LOGINFO)
    try:
        xbmc.executebuiltin('RunScript("{}","{}")'.format(addon, payload))
    except Exception:
        owner.clearProperty(key)
        raise
    return True


def launch_root(payload):
    data = json.loads(unquote(payload))
    addon = xbmcaddon.Addon()
    owner = xbmcgui.Window(10000)
    key = addon.getAddonInfo('id') + '.LaunchOwner'
    if owner.getProperty(key) != data['token']:
        return
    from . import intro
    startup = None
    login = False
    try:
        startup = intro.start(addon.getAddonInfo('path'))
        from resources.lib import plugin as core
        core.before_dispatch()
        if not core.api.logged_in:
            login = True
            return
        if startup.cancelled:
            return
        if addon.getAddonInfo('id') == 'slyguy.disney.plus.cleanui':
            core._open_cleanui_entry()
        else:
            from .controller import UIController
            controller = UIController()
            try:
                controller.open_home()
            finally:
                controller.end_transition()
    finally:
        try:
            if startup:
                startup.close()
            restore_origin(data['origin'])
        finally:
            if owner.getProperty(key) == data['token']:
                owner.clearProperty(key)
        if login:
            # This query bypasses the visual launcher and retains SlyGuy login.
            xbmc.executebuiltin('ActivateWindow(Videos,"plugin://{}/?_cleanui_native=1",return)'.format(addon.getAddonInfo('id')))
