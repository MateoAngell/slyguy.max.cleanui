"""Native finite animations only; no worker, network or focus ownership."""
import xbmc
from slyguy import userdata


def reduced():
    return bool(userdata.get('cleanui_reduce_animations', False))


def prepare(window):
    window.setProperty('cleanui.motion', 'false' if reduced() else 'true')


def animate(window, ids):
    if reduced() or xbmc.getCondVisibility('Player.HasVideo'):
        return
    for cid in ids:
        try:
            window.getControl(cid).setAnimations([
                ('Conditional', 'effect=fade start=65 end=100 time=150 condition=true reversible=false'),
                ('Conditional', 'effect=slide start=0,8 end=0,0 time=150 tween=cubic easing=out condition=true reversible=false'),
            ])
        except Exception:
            pass


def toggle(window):
    userdata.set('cleanui_reduce_animations', not reduced())
    prepare(window)


def label():
    return 'Reducir animaciones: ' + ('Sí' if reduced() else 'No')
