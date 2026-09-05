from .. import plugin as core
from .models import Card, Rail, Screen
from slyguy import userdata
from collections import OrderedDict
from copy import deepcopy
from functools import wraps
from time import monotonic
from .artwork import artwork_from_images, normalize_art
from . import constants as C
import xbmc


# HBO Max no expone un endpoint para recuperar metadatos de una película
# a partir de su ID. Los rows ya cargados se conservan durante la sesión
# para poder construir posteriormente su detalle.
def _copy_screen(value):
    # Source rows are read-only payloads. Keep their references while copying
    # mutable presentation state, so a cache hit does not clone the entire
    # relationship graph behind every visible card.
    memo = {}
    if isinstance(value, Screen):
        cards = ([value.hero] if value.hero else []) + [
            card for rail in value.rails for card in rail.items]
        for card in cards:
            if card.source_item is not None:
                memo[id(card.source_item)] = card.source_item
    return deepcopy(value, memo)


def cached_screen(seconds, copy_models=True):
    """Bounded per-session cache; windows always receive independent models."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            self._check_profile()
            key = (method.__name__, args, tuple(sorted(kwargs.items())))
            cached = self._cache.get(key)
            if cached and monotonic() - cached[0] < seconds:
                self._cache.move_to_end(key)
                return _copy_screen(cached[1]) if copy_models else cached[1]
            result = method(self, *args, **kwargs)
            self._cache[key] = (monotonic(), _copy_screen(result) if copy_models else result)
            self._cache.move_to_end(key)
            while len(self._cache) > 12:
                self._cache.popitem(last=False)
            return result
        return wrapped
    return decorate


class UIRepository(object):
    """Repository that translates HBO Max API data into Clean UI models."""

    def __init__(self, api_instance=None):
        self.api = api_instance or core.api
        self._cache = OrderedDict()
        self._raw_items = OrderedDict()
        self._profile_id = (userdata.get('profile') or {}).get('id')

    def _check_profile(self):
        profile_id = (userdata.get('profile') or {}).get('id')
        if profile_id != self._profile_id:
            self._cache.clear()
            self._raw_items.clear()
            self._profile_id = profile_id

    def refresh_continue_watching(self, screen):
        # This integration does not implement history synchronization.
        return False

    # ------------------------------------------------------------------
    # Pantallas principales (Home)
    # ------------------------------------------------------------------

    @cached_screen(60 * 5)
    def build_home(self):
        routes = self._menu_routes()
        if not routes:
            return Screen(
                screen_type=Screen.HOME,
                title='HBO Max',
                hero=None,
                rails=[],
                screen_kind='home',
            )

        data = self._route(routes[0])
        return self._screen_from_page(
            data=data,
            screen_type=Screen.HOME,
            title=data.get('title') or 'HBO Max',
            screen_kind='home',
            route=routes[0],
        )

    @cached_screen(60 * 5)
    def build_movies_home(self):
        return self._build_media_home(
            kind=Card.MOVIE,
            title='Películas',
            screen_kind='movies',
        )

    @cached_screen(60 * 5)
    def build_series_home(self):
        return self._build_media_home(
            kind=Card.SHOW,
            title='Series',
            screen_kind='series',
        )

    @cached_screen(60 * 2)
    def build_collection(self, id, title, page=1):
        data = self.api.collection(id, page=page)
        cards = self._cards_from_rows(data.get('items', []))
        self._add_next_page(cards, data, 'collection', (id, title, page + 1))
        rails = []
        if cards:
            rails.append(Rail(
                title=data.get('title') or title or '',
                items=cards,
                style=Rail.POSTER,
                rail_id=str(id),
            ))
        return Screen(
            screen_type=Screen.COLLECTION,
            title=title or data.get('title') or '',
            hero=cards[0] if cards else None,
            rails=rails,
            screen_kind='collection',
        )

    # ------------------------------------------------------------------
    # Detalles (Movie / Show / Season)
    # ------------------------------------------------------------------

    def build_movie_detail(self, id):
        self._check_profile()
        raw = self._raw_items.get(str(id))
        hero = None
        if raw:
            hero = self._card_from_raw(raw)

        if hero is None:
            hero = Card(
                label=str(id),
                kind=Card.MOVIE,
                art=self._normalize_art({}),
                info={'mediatype': 'movie'},
                play_path=core.plugin.url_for(core.play, id=id),
                deeplink_id=str(id),
                source_item=raw,
            )

        hero.kind = Card.MOVIE
        hero.deeplink_id = str(id)
        if not hero.play_path:
            hero.play_path = core.plugin.url_for(core.play, id=id)

        return Screen(
            screen_type=Screen.MOVIE,
            title=hero.label,
            hero=hero,
            rails=[],
            screen_kind='movie',
        )

    def build_show_detail(self, id):
        data = self.api.series(id)

        hero = self._card_from_raw({'show': data})

        if hero is None:
            hero = Card(
                label=data.get('name') or data.get('title') or str(id),
                kind=Card.SHOW,
                art=artwork_from_images(data.get('images', [])),
                info={
                    'mediatype': 'tvshow',
                    'plot': data.get('longDescription'),
                    'plotoutline': data.get('description'),
                },
                show_id=str(id),
                source_item=data,
            )

        hero.kind = Card.SHOW
        hero.show_id = str(id)

        # Build seasons rail
        seasons = []
        for season in sorted(
            (row for row in (data.get('seasons') or []) if isinstance(row, dict)),
            key=self._season_number,
        ):
            video_count = season.get('videoCountByType') or {}
            if str(video_count.get('EPISODE', '')).strip() == '0':
                continue

            season_number = season.get('seasonNumber')
            if season_number is None:
                continue

            display_name = season.get('displayName')
            if display_name is None:
                display_name = season_number

            info = {
                'mediatype': 'season',
                'season': season_number,
                'tvshowtitle': data.get('name') or data.get('title'),
                'plot': (
                    season.get('longDescription')
                    or data.get('longDescription')
                ),
                'plotoutline': (
                    season.get('description')
                    or data.get('description')
                ),
            }

            seasons.append(Card(
                label='Temporada {}'.format(display_name),
                kind=Card.SEASON,
                art=self._normalize_art(hero.art),
                info=info,
                open_path=core.plugin.url_for(
                    core.clean_ui_season,
                    show_id=id,
                    season_id=season_number,
                ),
                show_id=str(id),
                season_id=str(season_number),
                source_item=season,
            ))

        rails = []
        if seasons:
            rails.append(Rail(
                title='Temporadas',
                items=seasons,
                style=Rail.SEASON,
                rail_id='seasons',
            ))

        return Screen(
            screen_type=Screen.SHOW,
            title=hero.label,
            hero=hero,
            rails=rails,
            screen_kind='show',
        )

    def build_show_episodes(self, show_id, season_id=None, page=1):
        """Series detail with a real season selector and the selected episodes."""
        screen = self.build_show_detail(show_id)
        seasons = [card for rail in screen.rails for card in rail.items
                   if card.kind == Card.SEASON]
        screen.season_choices = seasons
        if not seasons:
            return screen
        selected = next((card for card in seasons if str(card.season_id) == str(season_id)), seasons[0])
        episode_screen = self.build_season_detail(show_id, selected.season_id, page)
        screen.rails = episode_screen.rails
        screen.selected_season = selected
        for rail in screen.rails:
            for card in rail.items:
                if card.kind == 'page':
                    card.source_item = ('show_episodes', (show_id, selected.season_id, page + 1))
        first = next((card for rail in screen.rails for card in rail.items
                      if card.kind == Card.EPISODE and card.play_path), None)
        if first:
            screen.hero.play_path = first.play_path
            screen.play_label = 'Ver T{} E{}'.format(selected.season_id, first.info.get('episode') or 1)
        return screen

    def build_season_detail(self, show_id, season_id, page=1):
        series_data = self.api.series(show_id)

        try:
            season_number = int(season_id)
        except (TypeError, ValueError):
            season_number = season_id

        # Find season metadata
        season_data = None
        for row in series_data.get('seasons', []):
            if str(row.get('seasonNumber')) == str(season_id):
                season_data = row
                season_number = row.get('seasonNumber')
                break

        data = self.api.season(show_id, season_number, page=page)
        episodes = self._cards_from_rows(data.get('items', []))
        self._add_next_page(episodes, data, 'season_detail', (show_id, season_id, page + 1))

        show_art = artwork_from_images(series_data.get('images', []))

        display_name = season_number
        if season_data and season_data.get('displayName') is not None:
            display_name = season_data.get('displayName')

        hero = Card(
            label='Temporada {}'.format(display_name),
            kind=Card.SEASON,
            art=show_art,
            info={
                'mediatype': 'season',
                'season': season_number,
                'tvshowtitle': (
                    series_data.get('name')
                    or series_data.get('title')
                ),
                'plot': (
                    (season_data or {}).get('longDescription')
                    or series_data.get('longDescription')
                ),
                'plotoutline': (
                    (season_data or {}).get('description')
                    or series_data.get('description')
                ),
            },
            show_id=str(show_id),
            season_id=str(season_number),
            source_item=season_data or series_data,
        )

        rails = []
        if episodes:
            rails.append(Rail(
                title='Episodios',
                items=episodes,
                style=Rail.EPISODE,
                rail_id='episodes',
            ))

        return Screen(
            screen_type=Screen.SEASON,
            title=hero.label,
            hero=hero,
            rails=rails,
            screen_kind='season',
        )

    # ------------------------------------------------------------------
    # Búsqueda y listas del usuario
    # ------------------------------------------------------------------

    def build_search(self, query, page=1):
        data = self.api.search(query=query, page=page)
        cards = self._cards_from_rows(
            data.get('items', []),
            from_search=True,
        )
        self._add_next_page(cards, data, 'search', (query, page + 1))

        rails = []
        if cards:
            rails.append(Rail(
                title='Resultados',
                items=cards,
                style=Rail.POSTER,
                rail_id='search',
            ))

        return Screen(
            screen_type=Screen.SEARCH,
            title=query,
            hero=cards[0] if cards else None,
            rails=rails,
            screen_kind='search',
        )

    def build_watchlist_screen(self, page=1):
        data = self.api.route('my-stuff')
        collection = core._find_collection(
            data,
            'my-stuff-page-rail-my-list',
        )
        if (collection and collection.get('id')
                and (page > 1 or not collection.get('items'))):
            collection = self.api.collection(collection['id'], page=page)
        rows = collection.get('items', []) if collection else []
        cards = self._cards_from_rows(rows, from_watchlist=True)
        self._add_next_page(cards, collection or {}, 'watchlist_screen', (page + 1,))

        rails = []
        if cards:
            rails.append(Rail(
                title='Mi lista',
                items=cards,
                style=Rail.POSTER,
                rail_id='watchlist',
            ))

        return Screen(
            screen_type=Screen.COLLECTION,
            title='Mi lista',
            hero=cards[0] if cards else None,
            rails=rails,
            screen_kind='watchlist',
        )

    def build_continue_watching_screen(self):
        # HBO Max no expone Continue Watching en la API.
        # Se devuelve una pantalla vacía para cumplir el contrato.
        return Screen(
            screen_type=Screen.COLLECTION,
            title='Continuar viendo',
            hero=None,
            rails=[],
            screen_kind='continue_watching',
        )

    # ------------------------------------------------------------------
    # Conversión de HBO Max a modelos Clean UI
    # ------------------------------------------------------------------

    def card_from_item(self, item, row=None):
        """Convert a SlyGuy plugin.Item to a Clean UI Card."""
        if item is None:
            return None

        label = getattr(item, 'label', None)
        path = getattr(item, 'path', None)
        info = dict(getattr(item, 'info', {}) or {})
        data = self._row_data(row)
        images = data.get('images') if isinstance(data, dict) else None
        inherited_art = getattr(item, 'art', {}) or {}
        parent_show = data.get('show') if isinstance(data, dict) else None
        if isinstance(parent_show, dict) and parent_show.get('images'):
            inherited_art = artwork_from_images(parent_show['images'], inherited_art)
        art = artwork_from_images(images, inherited_art)
        context = list(getattr(item, 'context', []) or [])

        if not label:
            return None

        mediatype = info.get('mediatype')
        data = self._row_data(row)
        content_id = data.get('id') if data else None

        show_id = ''
        season_id = ''
        browse_id = ''
        open_path = ''
        play_path = ''
        trailer_path = info.get('trailer') or ''
        kind = Card.VIDEO
        deeplink_id = ''

        if mediatype == 'movie':
            kind = Card.MOVIE
            if content_id is None:
                return None
            deeplink_id = str(content_id)
            play_path = path or core.plugin.url_for(core.play, id=content_id)
            open_path = core.plugin.url_for(core.clean_ui_movie, id=content_id)
            if row:
                self._raw_items[deeplink_id] = row
                self._raw_items.move_to_end(deeplink_id)
                while len(self._raw_items) > 500:
                    self._raw_items.popitem(last=False)

        elif mediatype == 'tvshow':
            kind = Card.SHOW
            if content_id is None:
                return None
            show_id = str(content_id)
            open_path = core.plugin.url_for(core.clean_ui_show, id=content_id)

        elif mediatype == 'season':
            kind = Card.SEASON
            show_id = str(
                (data or {}).get('show_id')
                or info.get('dbid')
                or ''
            )
            season_id = str(
                info.get('season')
                or ''
            )
            if show_id and season_id:
                open_path = core.plugin.url_for(
                    core.clean_ui_season,
                    show_id=show_id,
                    season_id=season_id,
                )
            else:
                open_path = path or ''

        elif mediatype == 'episode':
            kind = Card.EPISODE
            play_path = path or ''
            show = (data or {}).get('show') or {}
            if isinstance(show, dict) and show.get('id') is not None:
                show_id = str(show.get('id'))
            if (data or {}).get('seasonNumber') is not None:
                season_id = str(data.get('seasonNumber'))

        elif mediatype == 'video':
            kind = Card.VIDEO
            play_path = path or ''

        elif row and row.get('collection'):
            collection = row.get('collection') or {}
            collection_id = collection.get('id')
            if collection_id is None:
                return None
            kind = Card.COLLECTION
            browse_id = str(collection_id)
            open_path = path or core.plugin.url_for(
                core.collection,
                id=collection_id,
            )

        elif getattr(item, 'playable', False):
            kind = Card.VIDEO
            play_path = path or ''

        elif path:
            kind = Card.COLLECTION
            open_path = path
            if content_id is not None:
                browse_id = str(content_id)

        else:
            return None

        return Card(
            label=label,
            kind=kind,
            art=art,
            info=info,
            open_path=open_path,
            play_path=play_path,
            trailer_path=trailer_path,
            context=context,
            source_item=row or item,
            deeplink_id=deeplink_id,
            show_id=show_id,
            season_id=season_id,
            browse_id=browse_id,
        )

    def _card_from_raw(self, raw_item, from_search=False,
                       from_watchlist=False):
        """Convert raw HBO Max API data to a Card."""
        if not isinstance(raw_item, dict):
            return None

        # The original parser mutates data and evaluates name even when title
        # exists. Normalize an isolated row, leaving SlyGuy's parser intact.
        raw_item = deepcopy(raw_item)
        data = self._row_data(raw_item)
        if not isinstance(data, dict):
            return None
        data['name'] = data.get('name') or data.get('title') or ''
        if not data['name']:
            return None
        data['images'] = data.get('images') or []
        parent_show = data.get('show')
        if isinstance(parent_show, dict):
            parent_show['name'] = parent_show.get('name') or parent_show.get('title') or ''
            parent_show['images'] = parent_show.get('images') or []

        item = core.parse_row(
            raw_item,
            from_search=from_search,
            from_watchlist=from_watchlist,
        )
        if item is None:
            return None

        card = self.card_from_item(item, row=raw_item)
        if card is None or not card.label:
            return None

        if not (
            card.open_path
            or card.play_path
            or card.deeplink_id
            or card.show_id
            or card.browse_id
        ):
            return None

        return card

    def _normalize_art(self, art):
        return normalize_art(art)

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------

    @staticmethod
    def _season_number(row):
        try:
            return int(row.get('seasonNumber') or 0)
        except (TypeError, ValueError):
            return 0

    def _rail_from_items(self, items, title, style, rail_id='',
                         from_search=False, from_watchlist=False):
        cards = self._cards_from_rows(
            items,
            from_search=from_search,
            from_watchlist=from_watchlist,
        )
        if not cards:
            return None
        return Rail(
            title=title or '',
            items=cards,
            style=style,
            rail_id=rail_id or '',
        )

    def _cards_from_rows(self, rows, from_search=False,
                         from_watchlist=False):
        cards = []
        self._check_profile()
        for row in rows or []:
            try:
                card = self._card_from_raw(
                    row,
                    from_search=from_search,
                    from_watchlist=from_watchlist,
                )
            except (KeyError, TypeError, ValueError, AttributeError):
                xbmc.log('[CLEANUI] Skipped incomplete catalog item', xbmc.LOGWARNING)
                continue
            if card is not None:
                cards.append(card)
        return cards

    @staticmethod
    def _row_data(row):
        if not isinstance(row, dict):
            return {}
        return (
            row.get('show')
            or row.get('video')
            or row.get('taxonomyNode')
            or row.get('link')
            or row.get('collection')
            or {}
        )

    @cached_screen(60 * 10)
    def _menu_routes(self):
        """Get navigation routes from the web-menu-bar collection."""
        data = self._collection('web-menu-bar')
        routes = []
        for row in data.get('items', []):
            if row.get('hidden'):
                continue
            collection = row.get('collection') or {}
            if collection.get('name') in (
                'search-menu-item',
                'my-stuff-menu-item',
            ):
                continue
            items = collection.get('items', [])
            if not items:
                continue
            link = items[0].get('link') or {}
            linked_routes = link.get('linkedContentRoutes', [])
            if not linked_routes:
                continue
            route = linked_routes[0].get('url')
            if not route:
                continue
            route = route.lstrip('/')
            if route and route not in routes:
                routes.append(route)
        return routes

    def navigation_targets(self):
        """Expose only destinations actually supplied by the service menu."""
        targets = {}
        for row in self._collection('web-menu-bar').get('items', []):
            if row.get('hidden'):
                continue
            entry = row.get('collection') or {}
            name = '{} {}'.format(entry.get('name', ''), entry.get('title', '')).lower()
            key = ('hbo' if 'hbo' in name else
                   'kids' if any(x in name for x in ('kids', 'family', 'niños', 'familia')) else None)
            if key:
                for item in entry.get('items') or []:
                    routes = (item.get('link') or {}).get('linkedContentRoutes') or []
                    if routes and routes[0].get('url'):
                        targets[key] = routes[0]['url'].lstrip('/')
                        break
        return targets

    def build_navigation_section(self, key):
        route = self.navigation_targets().get(key)
        if not route:
            raise ValueError('This section is not available in the service menu')
        return self.build_route_page(route, title='HBO' if key == 'hbo' else 'Niños y Familia',
                                     screen_kind=key)

    @cached_screen(120, copy_models=False)
    def _route(self, route):
        return self.api.route(route)

    @cached_screen(120, copy_models=False)
    def _collection(self, collection_id):
        return self.api.collection(collection_id)

    @staticmethod
    def _more_card(builder, args, label='Ver más'):
        card = Card(label=label, kind='page', source_item=(builder, args))
        return card

    def _add_next_page(self, cards, data, builder, args):
        meta = data.get('meta') or {}
        try:
            more = int(meta.get('itemsCurrentPage', 1)) < int(meta.get('itemsTotalPages', 1))
        except (TypeError, ValueError):
            more = False
        if more:
            cards.append(self._more_card(builder, args, 'Página siguiente'))

    def build_next(self, card):
        builder, args = card.source_item
        allowed = {'collection', 'season_detail', 'show_episodes', 'search', 'route_page', 'watchlist_screen'}
        if builder not in allowed:
            raise ValueError('Unsupported page')
        return getattr(self, 'build_' + builder)(*args)

    def build_route_page(self, route, offset=0, kind=None, title='HBO Max', screen_kind='home'):
        return self._screen_from_page(self._route(route), Screen.HOME if screen_kind == 'home'
                                      else Screen.COLLECTION, title, screen_kind,
                                      route=route, offset=offset, kind=kind)

    def _screen_from_page(self, data, screen_type, title, screen_kind,
                          route=None, offset=0, kind=None):
        hero = None
        rails = []
        rows = data.get('items') or []
        next_offset = None
        # A bounded number of network requests per screen, even for sparse pages.
        scanned = 0
        fetched = 0
        for index in range(offset, len(rows)):
            row = rows[index]
            collection = row.get('collection') if isinstance(row, dict) else None
            if not isinstance(collection, dict) or row.get('hidden'):
                continue
            if len(rails) >= C.MAX_RAILS_HOME - 1 or scanned >= C.MAX_RAILS_HOME:
                next_offset = index
                break
            scanned += 1
            items = collection.get('items') or []
            if not items and collection.get('id'):
                if fetched >= 2:
                    next_offset = index
                    break
                fetched += 1
                try:
                    items = self._collection(collection['id']).get('items') or []
                except Exception:
                    xbmc.log('[CLEANUI] Collection unavailable', xbmc.LOGWARNING)
                    continue
            # Preview a bounded number of cards; full collections remain reachable.
            cards = self._cards_from_rows(items[:20])
            if kind:
                cards = [card for card in cards if card.kind == kind]
            if not cards:
                continue
            component = (collection.get('component') or {}).get('id')
            if hero is None:
                hero = cards[0]
            if collection.get('id'):
                cards.append(self._more_card('collection',
                    (str(collection['id']), collection.get('title') or '', 1),
                    'Ver colección completa'))
            rails.append(Rail(title=collection.get('title') or ('Destacados' if component == 'hero' else ''),
                              items=cards, style=Rail.POSTER,
                              rail_id=str(collection.get('id') or '')))
        if next_offset is not None and route:
            rails.append(Rail(title='Más categorías', style=Rail.POSTER, items=[
                self._more_card('route_page', (route, next_offset, kind, title, screen_kind),
                                'Ver más categorías')]))
        return Screen(screen_type=screen_type, title=title or '', hero=hero,
                      rails=rails, screen_kind=screen_kind)

    def _build_media_home(self, kind, title, screen_kind):
        routes = self._menu_routes()
        words = ('movie', 'film', 'pelicula', 'película') if kind == Card.MOVIE else ('series', 'show')
        selected = next((route for route in routes if any(word in route.lower() for word in words)), None)
        route = selected or (routes[0] if routes else None)
        if not route:
            return Screen(Screen.COLLECTION, title=title, screen_kind=screen_kind)
        return self.build_route_page(route, 0, None if selected else kind, title, screen_kind)

# Alias para compatibilidad con el controlador
Repository = UIRepository
