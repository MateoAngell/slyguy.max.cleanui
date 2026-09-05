"""UI artwork selection without rewriting the service's query parameters."""
from urllib.parse import urlsplit


KINDS = {
    'poster': ('poster-with-logo', 'poster', 'cover-artwork-vertical'),
    'thumb': ('cover-artwork-square', 'poster-with-logo', 'default', 'cover-artwork'),
    'fanart': ('default', 'default-wide', 'cover-artwork'),
    'clearlogo': ('logo-centered', 'content-logo-monochromatic', 'logo-left'),
}


def artwork_from_images(images, fallback=None):
    """Prefer raw URLs to the core's src + '?w=600' concatenation.

    Existing query strings can contain routing, crop and signature data. Keep
    them byte-for-byte. Plain URLs use only the 600px thumbnail request already
    used by the original add-on; do not invent a new CDN transformation.
    """
    art = dict(fallback or {})
    by_kind = {}
    for image in images or []:
        if isinstance(image, dict) and image.get('kind') and image.get('src'):
            by_kind.setdefault(image['kind'], image['src'])
    for key, kinds in KINDS.items():
        for kind in kinds:
            url = by_kind.get(kind)
            if not isinstance(url, str) or not url:
                continue
            parts = urlsplit(url)
            if key in ('poster', 'thumb', 'clearlogo') and parts.scheme in ('http', 'https'):
                if not parts.query and not parts.fragment and '|' not in url:
                    url += '?w=600'
            art[key] = url
            break
    return normalize_art(art)


def normalize_art(art):
    art = dict(art or {})
    for key, value in list(art.items()):
        if not isinstance(value, str):
            art[key] = ''
    poster = art.get('poster') or art.get('thumb') or art.get('fanart') or art.get('banner') or ''
    thumb = art.get('thumb') or poster
    fanart = art.get('fanart') or art.get('banner') or thumb
    art.update(poster=poster, thumb=thumb, fanart=fanart,
               banner=art.get('banner') or fanart, clearlogo=art.get('clearlogo') or '')
    return art
