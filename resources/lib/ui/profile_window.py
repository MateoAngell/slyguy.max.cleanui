"""TV profile picker; authentication and PIN remain in SlyGuy's core."""
import xbmcgui
from slyguy import userdata, gui
from . import constants as C


class ProfileWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.profiles = kwargs.pop('profiles')
        self.selected = None
        super(ProfileWindow, self).__init__(*args, **kwargs)

    def onInit(self):
        control = self.getControl(4100)
        control.reset()
        current = (userdata.get('profile') or {}).get('id')
        selected = 0
        items = []
        for i, profile in enumerate(self.profiles):
            item = xbmcgui.ListItem(label=profile.get('profileName') or '', offscreen=True)
            item.setArt({'thumb': profile.get('_avatar') or ''})
            items.append(item)
            if profile.get('id') == current:
                selected = i
        control.addItems(items)
        control.selectItem(selected)
        # Centre short profile lists, keeping longer lists scrollable.
        width = min(1500, max(300, len(items) * 280))
        control.setWidth(width)
        control.setPosition((1920 - width) // 2, 380)
        self.setFocus(control)

    def onClick(self, control_id):
        if control_id == 4100:
            position = self.getControl(4100).getSelectedPosition()
            if 0 <= position < len(self.profiles):
                self.selected = self.profiles[position]
                self.close()
        elif control_id == 1003:
            self.close()

    def onAction(self, action):
        if action.getId() in C.ACTION_BACK:
            self.close()


def choose_profile(addon_path):
    import resources.lib.plugin as core
    if userdata.get('kid_lockdown', False):
        return False
    with gui.busy():
        profiles = [dict(p) for p in core.api.profiles() if p.get('id')]
    for profile in profiles:
        profile['_avatar'] = ((profile.get('avatar') or {}).get('avatarImage') or {}).get('src') or ''
    if not profiles:
        return False
    window = ProfileWindow('ui_profiles.xml', addon_path, 'Default', '1080i', profiles=profiles)
    window.doModal()
    selected = window.selected
    del window
    if selected is None:
        return False
    if selected.get('id') != (userdata.get('profile') or {}).get('id'):
        # Preserve the existing secure switch, including PIN prompts.
        core._set_profile(selected, switching=True)
    return True
