"""Finish Kodi directory requests independently of the visual script."""
import json
import time
import uuid
from urllib.parse import quote, unquote

import xbmc
import xbmcaddon
import xbmcgui
from slyguy import plugin

RUNNING = 'MaxCleanUI.Running'
RUNNING_SINCE = 'MaxCleanUI.RunningSince'
METHODS = {'open_home', 'open_movie', 'open_show', 'open_season', 'open_search'}


def run(method, *args):
    if method not in METHODS:
        raise ValueError('Unsupported Clean UI entry')
    owner = xbmcgui.Window(10000)
    # Complete the directory request silently; the UI opens automatically.
    folder = plugin.Folder(cacheToDisc=False, no_items_label=None, show_news=False)
    active = owner.getProperty(RUNNING)
    # The controller remains alive while Kodi owns playback and its own
    # windows are intentionally closed.  Visibility is therefore not a
    # liveness check: clearing this token here can start a second profile UI
    # on top of a returning detail screen.  launch() owns token cleanup.
    if active:
        return folder
    token = uuid.uuid4().hex
    owner.setProperty(RUNNING, token)
    owner.setProperty(RUNNING_SINCE, str(time.time()))
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
            owner.clearProperty(RUNNING_SINCE)
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
        getattr(controller, method)(*args)
    finally:
        try:
            if controller:
                controller.end_transition()
        finally:
            if owner.getProperty(RUNNING) == token:
                owner.clearProperty(RUNNING)
                owner.clearProperty(RUNNING_SINCE)
