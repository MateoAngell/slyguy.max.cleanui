"""Internal UI host in the same addon; SlyGuy still resolves the streams."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if __name__ == '__main__':
    from resources.lib.ui.session import launch
    launch(sys.argv[1])
