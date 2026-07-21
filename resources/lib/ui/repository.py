from .. import plugin as core
from .models import Card, Rail, Screen
from slyguy import mem_cache


# HBO Max no expone un endpoint para recuperar metadatos de una película
# a partir de su ID. Los rows ya cargados se conservan durante la sesión
# para poder construir posteriormente su detalle.
_RAW_ITEMS = {}


class UIRepository(object):
    """Repository that translates HBO Max API data into Clean UI models."""

    def __init__(self, api_instance=None):
        self.api = api_instance or core.api

    # ------------------------------------------------------------------
    # Pantallas principales (Home)
    # ------------------------------------------------------------------

    @mem_cache.cached(60 * 5)
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

        data = self.api.route(routes[0])
        return self._screen_from_page(
            data=data,
            screen_type=Screen.HOME,
            title=data.get('title') or 'HBO Max',
            screen_kind='home',
        )

    @mem_cache.cached(60 * 5)
    def build_movies_home(self):
        return self._build_media_home(
            kind=Card.MOVIE,
            title='Películas',
            screen_kind='movies',
        )

    @mem_cache.cached(60 * 5)
    def build_series_home(self):
        return self._build_media_home(
            kind=Card.SHOW,
            title='Series',
            screen_kind='series',
        )

    @mem_cache.cached(60 * 2)
    def build_collection(self, id, title):
        data = self.api.collection(id)
        cards = self._cards_from_rows(data.get('items', []))
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
        raw = _RAW_ITEMS.get(str(id))
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

        hero_item = core.parse_row({'show': data})
        hero = self.card_from_item(hero_item, row={'show': data})

        if hero is None:
            hero = Card(
                label=data.get('name') or data.get('title') or str(id),
                kind=Card.SHOW,
                art=self._normalize_art(
                    core.get_art(data.get('images', []))
                ),
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
            data.get('seasons', []),
            key=lambda row: row.get('seasonNumber', 0),
        ):
            video_count = season.get('videoCountByType', {})
            if not video_count.get('EPISODE'):
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

    def build_season_detail(self, show_id, season_id):
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

        data = self.api.season(show_id, season_number)
        episodes = self._cards_from_rows(data.get('items', []))
        for ep in episodes:
            if ep.kind not in (Card.EPISODE, Card.VIDEO):
                ep.kind = Card.EPISODE

        show_art = self._normalize_art(
            core.get_art(series_data.get('images', []))
        )

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

    def build_search(self, query):
        data = self.api.search(query=query, page=1)
        cards = self._cards_from_rows(
            data.get('items', []),
            from_search=True,
        )

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

    def build_watchlist_screen(self):
        data = self.api.route('my-stuff')
        collection = core._find_collection(
            data,
            'my-stuff-page-rail-my-list',
        )
        rows = collection.get('items', []) if collection else []
        cards = self._cards_from_rows(rows, from_watchlist=True)

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
        art = self._normalize_art(
            dict(getattr(item, 'art', {}) or {})
        )
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
                _RAW_ITEMS[deeplink_id] = row

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
        if not raw_item:
            return None

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
        """Fill in missing art keys with fallbacks."""
        art = dict(art or {})
        poster = art.get('poster')
        thumb = art.get('thumb')
        fanart = art.get('fanart')
        banner = art.get('banner')
        clearlogo = art.get('clearlogo')

        poster = poster or thumb or fanart or banner or ''
        thumb = thumb or poster or fanart or banner or ''
        fanart = fanart or banner or thumb or poster or ''
        banner = banner or fanart or thumb or poster or ''
        clearlogo = clearlogo or ''

        art.update({
            'poster': poster,
            'thumb': thumb,
            'fanart': fanart,
            'banner': banner,
            'clearlogo': clearlogo,
        })
        return art

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------

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
        for row in rows or []:
            card = self._card_from_raw(
                row,
                from_search=from_search,
                from_watchlist=from_watchlist,
            )
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

    @mem_cache.cached(60 * 10)
    def _menu_routes(self):
        """Get navigation routes from the web-menu-bar collection."""
        data = self.api.collection('web-menu-bar')
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

    def _screen_from_page(self, data, screen_type, title, screen_kind):
        """Convert an HBO Max route page into a Screen."""
        hero = None
        rails = []

        for row in data.get('items', []):
            collection = row.get('collection')
            if not collection:
                continue

            component = collection.get('component') or {}
            component_id = component.get('id')
            rows = collection.get('items', [])

            # If no inline items, fetch from collection API
            if not rows and collection.get('id'):
                try:
                    collection_data = self.api.collection(
                        collection.get('id')
                    )
                    rows = collection_data.get('items', [])
                except Exception:
                    rows = []

            if component_id == 'hero':
                hero_cards = self._cards_from_rows(rows)
                if hero_cards and hero is None:
                    hero = hero_cards[0]
                continue

            if component_id == 'tab-group':
                tab_cards = self._cards_from_rows(rows)
                if tab_cards and hero is None:
                    hero = tab_cards[0]
                if tab_cards:
                    rails.append(Rail(
                        title=collection.get('title') or '',
                        items=tab_cards,
                        style=Rail.POSTER,
                        rail_id=str(collection.get('id') or ''),
                    ))
                continue

            rail = self._rail_from_items(
                items=rows,
                title=collection.get('title') or '',
                style=Rail.POSTER,
                rail_id=str(collection.get('id') or ''),
            )
            if rail:
                rails.append(rail)

        # Fallback hero from first rail item
        if hero is None:
            for rail in rails:
                if rail.items:
                    hero = rail.items[0]
                    break

        return Screen(
            screen_type=screen_type,
            title=title or '',
            hero=hero,
            rails=rails,
            screen_kind=screen_kind,
        )

    def _build_media_home(self, kind, title, screen_kind):
        """Build a media-specific home (movies/series) filtering by Card kind."""
        rails = []
        hero = None

        for route in self._menu_routes():
            try:
                data = self.api.route(route)
            except Exception:
                continue

            page = self._screen_from_page(
                data=data,
                screen_type=Screen.COLLECTION,
                title=data.get('title') or title,
                screen_kind=screen_kind,
            )

            for src_rail in page.rails:
                cards = [
                    card for card in src_rail.items
                    if card.kind == kind
                ]
                if not cards:
                    continue
                if hero is None:
                    hero = cards[0]
                rails.append(Rail(
                    title=src_rail.title,
                    items=cards,
                    style=src_rail.style,
                    rail_id=src_rail.rail_id,
                ))

        return Screen(
            screen_type=Screen.COLLECTION,
            title=title,
            hero=hero,
            rails=rails,
            screen_kind=screen_kind,
        )


# Alias para compatibilidad con el controlador
Repository = UIRepository
