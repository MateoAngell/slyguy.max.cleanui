"""Internal UI host in the same addon; SlyGuy still resolves the streams."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if __name__ == '__main__':
    from urllib.parse import unquote
    if unquote(sys.argv[1]).startswith('{'):
        from resources.lib.ui.entry import launch_root
        launch_root(sys.argv[1])
    else:
        from resources.lib.ui.session import launch
        launch(sys.argv[1])
