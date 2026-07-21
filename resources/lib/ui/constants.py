# Disney+ Clean UI - Constants

# Screen types
SCREEN_HOME = 'home'
SCREEN_MOVIE = 'movie_detail'
SCREEN_SHOW = 'show_detail'
SCREEN_SEASON = 'season_detail'
SCREEN_COLLECTION = 'collection'
SCREEN_SEARCH = 'search'

# Rail styles
STYLE_POSTER = 'poster'
STYLE_LANDSCAPE = 'landscape'
STYLE_EPISODE = 'episode'
STYLE_SEASON = 'season'
STYLE_BUTTON = 'button'
STYLE_BRAND = 'brand'

# Card kinds
KIND_MOVIE = 'movie'
KIND_SHOW = 'show'
KIND_SEASON = 'season'
KIND_EPISODE = 'episode'
KIND_COLLECTION = 'collection'
KIND_VIDEO = 'video'

# Control IDs
CONTROL_PLAY = 1000
CONTROL_TRAILER = 1001
CONTROL_WATCHLIST = 1002
CONTROL_BACK = 1003
CONTROL_MOVIES = 3001
CONTROL_SERIES = 3002
CONTROL_MENU = 3000
CONTROL_PROFILE = 3003
CONTROL_RAIL_FIRST = 4000

# Max rails per window. Home must contain XML controls 4000-4023.
MAX_RAILS_HOME = 24
MAX_RAILS_DETAIL = 4

# Fetch extra containers because heroes, brands, sports and premium
# promotional categories are filtered before constructing Home.
HOME_CONTAINER_FETCH = 60
HOME_ITEM_LIMIT = 30

# Property prefix
PROP_PREFIX = 'cleanui'

# Action codes
ACTION_SELECT = (7, 100)
ACTION_BACK = (9, 10, 92)
ACTION_MENU = (117, 122)
ACTION_LEFT = (1,)
ACTION_RIGHT = (2,)
ACTION_UP = (3,)
ACTION_DOWN = (4,)
