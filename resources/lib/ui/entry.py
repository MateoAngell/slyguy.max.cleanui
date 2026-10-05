"""Lightweight root launcher: no service imports while Kodi opens a directory."""
import json
import sys
import uuid
from urllib.parse import unquote

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
    origin = capture_origin()
    # Finish the directory before activating our normal window. Continue in
    # this interpreter: a second RunScript leaves Kodi visible between hosts.
    xbmcplugin.endOfDirectory(int(sys.argv[1]), succeeded=False, cacheToDisc=False)
    launch_root(origin=origin)
    return True


def repair_root_favourite(addon):
    """Replace only this add-on's root shortcut through Kodi, with a backup."""
    import xbmcvfs
    from urllib.parse import urlsplit

    def rpc(method, params):
        response = json.loads(xbmc.executeJSONRPC(json.dumps(dict(
            jsonrpc='2.0', id=1, method=method, params=params))))
        if 'error' in response:
            raise RuntimeError('Favourite update rejected')
        return response.get('result')

    addon_id = addon.getAddonInfo('id')
    try:
        favourites = rpc('Favourites.GetFavourites', dict(properties=[
            'path', 'window', 'windowparameter', 'thumbnail']))['favourites']
        targets = []
        for favourite in favourites:
            path = urlsplit(favourite.get('windowparameter') or '')
            if (favourite.get('type') == 'window' and path.scheme == 'plugin'
                    and path.netloc == addon_id and path.path in ('', '/')
                    and not path.query and not path.fragment):
                targets.append(favourite)
        if len(targets) != 1:
            return False
        # Do not toggle a separately created direct favourite or other routes.
        if any(f.get('type') == 'script' and
               f.get('path') in (addon_id, 'script://' + addon_id)
               for f in favourites):
            return False
        original = targets[0]
        profile = addon.getAddonInfo('profile')
        xbmcvfs.mkdirs(profile)
        backup = profile.rstrip('/\\') + '/favourites-before-direct-' + uuid.uuid4().hex + '.xml'
        if not xbmcvfs.copy('special://profile/favourites.xml', backup):
            return False
        direct = dict(title=original['title'], type='script', path=addon_id,
                      thumbnail=original.get('thumbnail') or '')
        # Create first. If creation fails the original remains untouched.
        rpc('Favourites.AddFavourite', direct)
        try:
            rpc('Favourites.AddFavourite', {k: original[k] for k in
                ('title', 'type', 'window', 'windowparameter', 'thumbnail') if k in original})
        except Exception:
            rpc('Favourites.AddFavourite', direct)  # rollback our new shortcut
            raise
        xbmc.log('[CLEANUI][ENTRY] Root favourite now opens the UI directly', xbmc.LOGINFO)
        return True
    except Exception:
        xbmc.log('[CLEANUI][ENTRY] Favourite unchanged; directory entry remains available', xbmc.LOGWARNING)
        return False


def launch_root(payload=None, origin=None):
    addon = xbmcaddon.Addon()
    owner = xbmcgui.Window(10000)
    key = addon.getAddonInfo('id') + '.LaunchOwner'
    if payload:
        data = json.loads(unquote(payload))
        if owner.getProperty(key) != data['token']:
            return
    else:
        if (owner.getProperty(key) or owner.getProperty('MaxCleanUI.Running')
                or owner.getProperty('DisneyPlusCleanUI.Running')):
            return
        data = dict(token=uuid.uuid4().hex, origin=origin or capture_origin())
        owner.setProperty(key, data['token'])
    startup = None
    login = False
    try:
        from . import intro
        startup = intro.start(addon.getAddonInfo('path'))
        repair_root_favourite(addon)
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
