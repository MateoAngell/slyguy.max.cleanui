"""Finish Kodi directory requests independently of the visual script."""
import json
import uuid
from urllib.parse import quote, unquote

import xbmc
import xbmcaddon
import xbmcgui
from slyguy import plugin

RUNNING = 'MaxCleanUI.Running'
METHODS = {'open_home', 'open_movie', 'open_show', 'open_season', 'open_search'}


def run(method, *args):
    if method not in METHODS:
        raise ValueError('Unsupported Clean UI entry')
    owner = xbmcgui.Window(10000)
    folder = plugin.Folder(cacheToDisc=False)
    # Re-enter the UI, never special://home (Kodi's internal addon files).
    folder.add_item(label='Abrir HBO Max Clean UI',
                    path='plugin://slyguy.max.cleanui/', bookmark=False)
    if owner.getProperty(RUNNING):
        return folder
    token = uuid.uuid4().hex
    owner.setProperty(RUNNING, token)
    payload = quote(json.dumps([method, args, token]), safe='')
    # Run the addon library extension by ID so Kodi supplies its dependency
    # paths and addon identity. Running a loose .py loses that context.
    script = xbmcaddon.Addon().getAddonInfo('id')
    try:
        xbmc.executebuiltin('RunScript("{}","{}")'.format(
            script.replace('"', '\\"'), payload))
    except Exception:
        if owner.getProperty(RUNNING) == token:
            owner.clearProperty(RUNNING)
        raise
    return folder


def launch(payload):
    method, args, token = json.loads(unquote(payload))
    if method not in METHODS:
        raise ValueError('Unsupported Clean UI entry')
    owner = xbmcgui.Window(10000)
    if owner.getProperty(RUNNING) != token:
        return
    controller = None
    try:
        from resources.lib import plugin as core
        # Use the original initializer, as the plugin dispatcher does.
        core.before_dispatch()
        from .controller import UIController
        controller = UIController()
        if method == 'open_home' and not controller.select_start_profile():
            return
        getattr(controller, method)(*args)
    finally:
        try:
            if controller:
                controller.end_transition()
        finally:
            if owner.getProperty(RUNNING) == token:
                owner.clearProperty(RUNNING)
