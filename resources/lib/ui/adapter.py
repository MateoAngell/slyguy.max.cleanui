import xbmcgui

from . import constants as C
from ..constants import CONTINUE_WATCHING_ID
from .models import Card


class UIAdapter(object):
    """Converts Card models to Kodi ListItems for display in XML windows."""

    @staticmethod
    def get_kind(item):
        """Determine content kind from a Slyguy plugin.Item."""
        info = getattr(item, 'info', {}) or {}
        media_type = info.get('mediatype', '')

        if media_type == 'movie':
            return Card.MOVIE
        elif media_type == 'tvshow':
            return Card.SHOW
        elif media_type == 'season':
            return Card.SEASON
        elif media_type == 'episode':
            return Card.EPISODE
        elif media_type in ('video', 'musicvideo'):
            return Card.VIDEO
        else:
            return Card.COLLECTION

    @staticmethod
    def normalize_rail_style(value, default='poster'):
        """Normalize a rail style value, preserving valid styles."""
        value = str(value or '').strip().lower()
        aliases = {
            'episodes': 'episode',
            'brands': 'brand',
            'industry': 'brand',
            'industries': 'brand',
            'seasons': 'season',
        }
        value = aliases.get(value, value)
        if value in ('poster', 'episode', 'landscape', 'season', 'brand'):
            return value
        return default

    @staticmethod
    def _effective_rail_style(rail, screen_kind=None):
        """Return the visual style without depending on rail position."""
        source_style = str(
            getattr(rail, 'style', '') or C.STYLE_POSTER
        ).strip().lower()
        screen_kind = str(
            screen_kind or ''
        ).strip().lower()
        rail_id = str(
            getattr(rail, 'rail_id', '') or ''
        ).strip()

        # Industrias siempre usan su diseno Brand.
        if source_style == C.STYLE_BRAND:
            return C.STYLE_BRAND

        # En Home, unicamente Continue Watching es panoramico.
        if screen_kind == C.SCREEN_HOME:
            if rail_id == CONTINUE_WATCHING_ID:
                return C.STYLE_LANDSCAPE
            return C.STYLE_POSTER

        # Pantalla dedicada de Continuar viendo.
        if screen_kind == 'continue_watching':
            return C.STYLE_LANDSCAPE

        # Peliculas, Series, Mi lista e Industrias usan poster.
        if screen_kind in (
            'movies',
            'series',
            'watchlist',
            'collection',
        ):
            return C.STYLE_POSTER

        # DetailWindow puede preservar estilos explicitos.
        if source_style in (
            C.STYLE_LANDSCAPE,
            C.STYLE_EPISODE,
            C.STYLE_SEASON,
        ):
            return source_style
        return C.STYLE_POSTER

    @staticmethod
    def to_list_item(card, rail_style=C.STYLE_POSTER):
        """Convert a Card to a Kodi ListItem."""

        li = xbmcgui.ListItem(
            label=card.label or '',
            offscreen=True,
        )

        # Set art - choose best artwork per rail style
        art = card.art or {}
        brand_logo = ''
        brand_background = ''
        if rail_style == C.STYLE_EPISODE:
            display_thumb = (
                art.get('thumb')
                or art.get('thumbnail')
                or art.get('fanart')
                or art.get('banner')
                or art.get('keyart')
                or art.get('poster')
                or ''
            )
        elif rail_style == C.STYLE_LANDSCAPE:
            display_thumb = (
                art.get('thumb')
                or art.get('banner')
                or art.get('fanart')
                or art.get('keyart')
                or art.get('poster')
                or ''
            )
        elif rail_style == C.STYLE_BRAND:
            brand_logo = art.get('clearlogo') or ''
            brand_background = (
                art.get('thumb')
                or art.get('banner')
                or art.get('fanart')
                or art.get('keyart')
                or art.get('poster')
                or ''
            )
            display_thumb = brand_background or brand_logo
        else:
            # Poster y temporada deben preferir arte vertical.
            display_thumb = (
                art.get('poster')
                or art.get('keyart')
                or art.get('thumb')
                or art.get('fanart')
                or art.get('banner')
                or ''
            )
        li.setArt({
            'poster': (
                art.get('poster')
                or art.get('keyart')
                or display_thumb
            ),
            'thumb': display_thumb,
            'fanart': (
                art.get('fanart')
                or art.get('banner')
                or art.get('thumb')
                or display_thumb
            ),
            'banner': (
                art.get('banner')
                or art.get('fanart')
                or art.get('thumb')
                or display_thumb
            ),
            'clearlogo': brand_logo or art.get('clearlogo', ''),
        })

        # Set info
        li.setInfo('video', card.info or {})

        # Set CleanUI properties
        li.setProperty('{}.kind'.format(C.PROP_PREFIX), card.kind)
        li.setProperty('{}.open_path'.format(C.PROP_PREFIX), card.open_path)
        li.setProperty('{}.play_path'.format(C.PROP_PREFIX), card.play_path)
        li.setProperty('{}.trailer_path'.format(C.PROP_PREFIX), card.trailer_path)
        li.setProperty('{}.rail_style'.format(C.PROP_PREFIX), rail_style)
        li.setProperty(
            '{}.display_art'.format(C.PROP_PREFIX),
            display_thumb,
        )
        li.setProperty(
            '{}.brand_logo'.format(C.PROP_PREFIX),
            brand_logo if rail_style == C.STYLE_BRAND else '',
        )
        li.setProperty(
            '{}.brand_background'.format(C.PROP_PREFIX),
            brand_background if rail_style == C.STYLE_BRAND else '',
        )
        li.setProperty(
            '{}.brand_has_logo'.format(C.PROP_PREFIX),
            'true'
            if rail_style == C.STYLE_BRAND and brand_logo
            else 'false',
        )
        li.setProperty('{}.is_playable'.format(C.PROP_PREFIX),
                       'true' if card.play_path else 'false')
        # Estilos explicitos para condiciones XML claras
        li.setProperty('{}.is_episode'.format(C.PROP_PREFIX),
                       'true' if rail_style == C.STYLE_EPISODE else 'false')
        li.setProperty('{}.is_landscape'.format(C.PROP_PREFIX),
                       'true' if rail_style == C.STYLE_LANDSCAPE else 'false')
        li.setProperty('{}.is_wide'.format(C.PROP_PREFIX),
                       'true' if rail_style in (C.STYLE_LANDSCAPE, C.STYLE_EPISODE) else 'false')
        li.setProperty('{}.is_brand'.format(C.PROP_PREFIX),
                       'true' if rail_style == C.STYLE_BRAND else 'false')
        # Direct IDs for navigation (avoids URL re-parsing)
        li.setProperty('{}.deeplink_id'.format(C.PROP_PREFIX), card.deeplink_id)
        li.setProperty('{}.show_id'.format(C.PROP_PREFIX), card.show_id)
        li.setProperty('{}.season_id'.format(C.PROP_PREFIX), card.season_id)
        li.setProperty('{}.browse_id'.format(C.PROP_PREFIX), card.browse_id)
        li.setProperty('{}.browse_ref'.format(C.PROP_PREFIX), card.browse_ref)

        return li

    @staticmethod
    def extract_cleanui_properties(item):
        """Extract CleanUI properties from a ListItem."""
        return {
            'kind': item.getProperty('{}.kind'.format(C.PROP_PREFIX)),
            'open_path': item.getProperty('{}.open_path'.format(C.PROP_PREFIX)),
            'play_path': item.getProperty('{}.play_path'.format(C.PROP_PREFIX)),
            'trailer_path': item.getProperty('{}.trailer_path'.format(C.PROP_PREFIX)),
        }
