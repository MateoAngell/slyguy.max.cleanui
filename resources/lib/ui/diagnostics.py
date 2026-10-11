"""Optional, fail-open technical events. No files, network or extra workers."""
import json
import time
import xbmc
import xbmcaddon
import xbmcgui

_session = ''
_directions = 0
_last_direction = 0.0


def emit(event, **values):
    global _session
    try:
        home = xbmcgui.Window(10000)
        if not home.getProperty('cleanui.diagnostics.owner'):
            return
        addon = xbmcaddon.Addon().getAddonInfo('id')
        _session = home.getProperty(addon + '.LaunchOwner') or _session
        # Only fixed screen enums and numeric counters, never content/account data.
        data = {k: v for k, v in values.items() if isinstance(v, (int, float, bool))}
        if values.get('screen') in ('home', 'movies', 'series', 'collection',
                'detail', 'movie', 'show', 'season', 'episodes', 'search', 'watchlist', 'profiles'):
            data['screen'] = values['screen']
        xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0', id=1,
            method='JSONRPC.NotifyAll', params=dict(sender='cleanui.diagnostics',
                message='cleanui.diagnostics.event',
                data=dict(addon=addon, session=_session, event=event, data=data)))))
    except Exception:
        pass


def direction(action):
    global _directions, _last_direction
    if action not in (1, 2, 3, 4):
        return
    _directions += 1
    now = time.monotonic()
    if now - _last_direction >= 5:
        emit('directions', count=_directions)
        _directions, _last_direction = 0, now
