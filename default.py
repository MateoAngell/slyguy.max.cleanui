import os
import xbmc
import xbmcvfs

# Deploy keymap for simple player controls (like Disney+ web)
_KEYMAP_PATH = 'special://profile/keymaps/'
_KEYMAP_FILE = 'slyguy_cleanui_player.xml'
_KEYMAP_CONTENT = '''<?xml version="1.0" encoding="UTF-8"?>
<keymap>
  <FullscreenVideo>
    <keyboard>
      <space>PlayPause</space>
      <return>PlayPause</return>
      <enter>PlayPause</enter>
      <pause>PlayPause</pause>
      <left>StepBack</left>
      <right>StepForward</right>
      <up>OSD</up>
      <down>OSD</down>
      <escape>Stop</escape>
      <backspace>Stop</backspace>
      <plus>VolumeUp</plus>
      <minus>VolumeDown</minus>
    </keyboard>
    <remote>
      <up>OSD</up>
      <down>OSD</down>
      <left>StepBack</left>
      <right>StepForward</right>
      <select>PlayPause</select>
      <back>Stop</back>
    </remote>
    <universalremote>
      <up>OSD</up>
      <down>OSD</down>
      <left>StepBack</left>
      <right>StepForward</right>
    </universalremote>
  </FullscreenVideo>
</keymap>'''

def _deploy_keymap():
    try:
        keymap_dir = xbmcvfs.translatePath(_KEYMAP_PATH)
        if not os.path.exists(keymap_dir):
            os.makedirs(keymap_dir, exist_ok=True)
        dest = os.path.join(keymap_dir, _KEYMAP_FILE)
        if not os.path.exists(dest):
            with open(dest, 'w') as f:
                f.write(_KEYMAP_CONTENT)
            xbmc.log('[CLEANUI] Keymap player_simple instalado en {}'.format(dest), xbmc.LOGINFO)
    except Exception as exc:
        xbmc.log('[CLEANUI] No se pudo instalar keymap: {}'.format(exc), xbmc.LOGWARNING)

_deploy_keymap()

from resources.lib.plugin import plugin
plugin.dispatch()
