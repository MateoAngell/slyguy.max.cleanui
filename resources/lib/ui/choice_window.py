"""Small remote-friendly choice dialog shared by seasons and navigation."""
import xbmcgui
from . import constants as C


class ChoiceWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.title = kwargs.pop('title')
        self.options = kwargs.pop('options')
        self.selected = -1
        super(ChoiceWindow, self).__init__(*args, **kwargs)

    def onInit(self):
        self.setProperty('cleanui.choice.title', self.title)
        control = self.getControl(4100)
        control.addItems([xbmcgui.ListItem(label=text, offscreen=True) for text in self.options])
        self.setFocus(control)

    def onClick(self, cid):
        if cid == 4100:
            index = self.getControl(cid).getSelectedPosition()
            if 0 <= index < len(self.options):
                self.selected = index
                self.close()

    def onAction(self, action):
        if action.getId() in C.ACTION_BACK:
            self.close()


def choose(addon_path, title, options):
    if not options:
        return -1
    window = ChoiceWindow('ui_choice.xml', addon_path, 'Default', '1080i', title=title, options=options)
    window.doModal()
    selected = window.selected
    del window
    return selected
