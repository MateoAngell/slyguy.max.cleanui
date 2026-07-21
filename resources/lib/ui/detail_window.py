import time
import traceback

import xbmc
import xbmcgui

from .adapter import UIAdapter
from . import constants as C


class DetailWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *a, **kw):
        self.controller = kw.pop('controller')
        self.screen = kw.pop('screen')
        super(DetailWindow, self).__init__(*a, **kw)
        self._last_activation = None

    def onInit(self):
        # La cortina la retira el controlador vía onFocus() (handshake de foco),
        # no aquí: retirarla en onInit dejaría la ventana de Vídeos expuesta
        # durante los frames en que la nueva ventana aún no se compone.
        try:
            self._reset_properties()
            self._set_hero()
            self._populate_rails()
            if not self._restore_state():
                self._focus_best()
        except Exception:
            self._log_error('onInit')
            if self.controller:
                self.controller.end_transition()
            try:
                self.close()
            except Exception:
                pass

    def onFocus(self, control_id):
        # Handshake de transición: notifica al controlador que esta ventana
        # recuperó el foco. El controlador solo retira la cortina si esta
        # ventana era el destino de la transición (ventana padre al volver de
        # una hija, o última ventana restaurada tras reproducción).
        if self.controller:
            self.controller.notify_window_focused(self)

    def capture_state(self):
        if not self.screen:
            return

        state = {
            'focus_id': -1,
            'positions': {},
        }

        try:
            state['focus_id'] = self.getFocusId()
        except Exception:
            pass

        for index in range(C.MAX_RAILS_DETAIL):
            control_id = C.CONTROL_RAIL_FIRST + index
            try:
                control = self.getControl(control_id)
                if control.size() > 0:
                    state['positions'][control_id] = (
                        control.getSelectedPosition()
                    )
            except Exception:
                continue

        self.screen._cleanui_window_state = state

        xbmc.log(
            '[CLEANUI] Estado de detalle guardado: tipo={}, '
            'foco={}, posiciones={}'.format(
                getattr(self.screen, 'screen_type', 'unknown'),
                state['focus_id'],
                state['positions'],
            ),
            xbmc.LOGINFO,
        )

    def _restore_state(self):
        if not self.screen:
            return False

        state = getattr(
            self.screen,
            '_cleanui_window_state',
            None,
        )

        if not state:
            return False

        positions = state.get('positions') or {}

        for control_id, position in positions.items():
            try:
                control = self.getControl(control_id)
                if control.size() <= 0:
                    continue
                position = int(position)
                if position < 0:
                    position = 0
                if position >= control.size():
                    position = control.size() - 1
                control.selectItem(position)
            except Exception:
                continue

        focus_id = state.get('focus_id', -1)

        try:
            control = self.getControl(focus_id)
            if (
                C.CONTROL_RAIL_FIRST
                <= focus_id
                < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_DETAIL
                and control.size() <= 0
            ):
                return False
            self.setFocus(control)
            xbmc.log(
                '[CLEANUI] Estado de detalle restaurado: tipo={}, '
                'foco={}, posiciones={}'.format(
                    getattr(self.screen, 'screen_type', 'unknown'),
                    focus_id,
                    positions,
                ),
                xbmc.LOGINFO,
            )
            return True
        except Exception:
            xbmc.log(
                '[CLEANUI] No se pudo restaurar el foco exacto del detalle',
                xbmc.LOGWARNING,
            )
            return False

    def _log_error(self, context):
        xbmc.log(
            '[CLEANUI] DetailWindow.{}:\n{}'.format(
                context,
                traceback.format_exc(),
            ),
            xbmc.LOGERROR,
        )

    def _reset_properties(self):
        prefix = C.PROP_PREFIX

        for name in (
            'title',
            'fanart',
            'poster',
            'logo',
            'plot',
            'play_path',
            'trailer_path',
            'watchlist_action',
            'kind',
            'meta',
            'genre',
        ):
            self.setProperty(
                '{}.detail.{}'.format(prefix, name),
                '',
            )

        for index in range(C.MAX_RAILS_DETAIL):
            self.setProperty(
                '{}.detail.rail{}.visible'.format(
                    prefix,
                    index,
                ),
                'false',
            )
            self.setProperty(
                '{}.detail.rail{}.title'.format(
                    prefix,
                    index,
                ),
                '',
            )

    def _set_hero(self):
        h = self.screen.hero
        if not h:
            return

        p = C.PROP_PREFIX
        info = h.info or {}
        art = h.art or {}

        self.setProperty('{}.detail.title'.format(p), h.label or '')
        self.setProperty('{}.detail.fanart'.format(p),
                         art.get('fanart', '') or art.get('banner', '') or art.get('thumb', ''))
        self.setProperty('{}.detail.poster'.format(p),
                         art.get('poster', '') or art.get('thumb', ''))
        self.setProperty('{}.detail.logo'.format(p), art.get('clearlogo', ''))
        self.setProperty('{}.detail.plot'.format(p), info.get('plot', '') or '')
        self.setProperty('{}.detail.play_path'.format(p), h.play_path or '')
        self.setProperty('{}.detail.trailer_path'.format(p), h.trailer_path or '')
        self.setProperty('{}.detail.kind'.format(p), h.kind or '')

        # Watchlist action from context menu
        watch_act = ''
        for lb, act in (h.context or []):
            s = (lb or '').lower()
            if 'watchlist' in s or 'lista' in s or 'guardar' in s:
                watch_act = act
                break
        self.setProperty('{}.detail.watchlist_action'.format(p), watch_act)

        parts = []
        y = info.get('year')
        if y:
            parts.append(str(y))
        mpaa = info.get('mpaa', info.get('rating', ''))
        if mpaa:
            parts.append(str(mpaa))
        try:
            duration = max(
                0,
                int(info.get('duration') or 0),
            )
        except (TypeError, ValueError):
            duration = 0
        if duration:
            minutes = duration // 60
            hours, minutes = divmod(minutes, 60)
            parts.append(
                '{}h {}m'.format(hours, minutes)
                if hours
                else '{}m'.format(minutes)
            )
        self.setProperty('{}.detail.meta'.format(p), ' • '.join(parts))

        g = info.get('genre', '')
        if isinstance(g, (list, tuple)):
            g = ', '.join(str(x) for x in g)
        self.setProperty('{}.detail.genre'.format(p), str(g))

    def _populate_rails(self):
        p = C.PROP_PREFIX
        for i in range(C.MAX_RAILS_DETAIL):
            cid = C.CONTROL_RAIL_FIRST + i
            try:
                control = self.getControl(cid)
            except RuntimeError:
                xbmc.log(
                    '[CLEANUI] No existe el control del rail de detalle: {}'.format(
                        cid
                    ),
                    xbmc.LOGWARNING,
                )
                continue

            control.reset()

            visible_property = '{}.detail.rail{}.visible'.format(p, i)
            title_property = '{}.detail.rail{}.title'.format(p, i)

            if i >= len(self.screen.rails):
                self.setProperty(visible_property, 'false')
                self.setProperty(title_property, '')
                continue

            rail = self.screen.rails[i]
            if not rail or not rail.items:
                self.setProperty(visible_property, 'false')
                self.setProperty(title_property, '')
                continue

            effective_style = UIAdapter._effective_rail_style(
                rail, self.screen.screen_type
            )

            list_items = []
            inserted_cards = []
            failed = 0
            first_error = None
            for index, card in enumerate(rail.items):
                try:
                    list_item = UIAdapter.to_list_item(
                        card,
                        effective_style,
                    )
                    if list_item:
                        list_items.append(list_item)
                        inserted_cards.append(card)
                except Exception:
                    failed += 1
                    if first_error is None:
                        first_error = traceback.format_exc()
            if failed:
                xbmc.log(
                    '[CLEANUI] Rail de detalle {!r}: {} tarjetas fallaron '
                    'al convertir. Primer error:\n{}'.format(
                        getattr(rail, 'title', ''),
                        failed,
                        first_error,
                    ),
                    xbmc.LOGERROR,
                )

            if not list_items:
                self.setProperty(visible_property, 'false')
                self.setProperty(title_property, '')
                xbmc.log(
                    '[CLEANUI] Rail de detalle descartado porque ninguna '
                    'tarjeta pudo mostrarse; rail={}, titulo={!r}'.format(
                        i,
                        getattr(rail, 'title', ''),
                    ),
                    xbmc.LOGWARNING,
                )
                continue

            try:
                control.addItems(list_items)
            except Exception:
                self.setProperty(visible_property, 'false')
                self.setProperty(title_property, '')
                xbmc.log(
                    '[CLEANUI] No se pudieron insertar las tarjetas en el '
                    'rail de detalle {}:\n{}'.format(
                        i,
                        traceback.format_exc(),
                    ),
                    xbmc.LOGERROR,
                )
                continue

            # Mantener el modelo sincronizado con las tarjetas visibles.
            rail.items = inserted_cards

            self.setProperty(visible_property, 'true')
            self.setProperty(title_property, rail.title or '')

    def _focus_best(self):
        """Focus the first visible, populated rail."""
        for i in range(C.MAX_RAILS_DETAIL):
            control_id = C.CONTROL_RAIL_FIRST + i
            try:
                control = self.getControl(control_id)
                if control.size() <= 0:
                    continue
                if not control.isVisible():
                    continue
                if control.getSelectedPosition() < 0:
                    control.selectItem(0)
                self.setFocus(control)
                return
            except RuntimeError:
                continue

        p = C.PROP_PREFIX
        candidates = (
            ('{}.detail.play_path'.format(p), C.CONTROL_PLAY),
            ('{}.detail.trailer_path'.format(p), C.CONTROL_TRAILER),
            ('{}.detail.watchlist_action'.format(p), C.CONTROL_WATCHLIST),
        )
        for property_name, control_id in candidates:
            if not self.getProperty(property_name):
                continue
            try:
                control = self.getControl(control_id)
                if control.isVisible():
                    self.setFocus(control)
                    return
            except RuntimeError:
                continue

        try:
            self.setFocus(self.getControl(C.CONTROL_BACK))
        except RuntimeError:
            pass

    def _is_duplicate_activation(self, cid):
        try:
            position = self.getControl(cid).getSelectedPosition()
        except Exception:
            position = -1

        key = (cid, position)
        now = time.monotonic()

        if self._last_activation:
            prev_key, prev_time = self._last_activation
            if prev_key == key and now - prev_time < 0.6:
                return True

        self._last_activation = (key, now)
        return False

    def _close_current_window(self):
        if self.controller:
            self.controller.close_child_window(self)
        else:
            self.close()

    def onClick(self, cid):
        if cid == C.CONTROL_BACK:
            self._close_current_window()
            return

        if self._is_duplicate_activation(cid):
            return

        p = C.PROP_PREFIX

        if cid == C.CONTROL_PLAY:
            self._play(self.getProperty('{}.detail.play_path'.format(p)))
            return

        if cid == C.CONTROL_TRAILER:
            self._play(self.getProperty('{}.detail.trailer_path'.format(p)))
            return

        if cid == C.CONTROL_WATCHLIST:
            act = self.getProperty(
                '{}.detail.watchlist_action'.format(p)
            )
            if not act:
                return
            try:
                xbmc.executebuiltin(act)
            except Exception:
                self._log_error('onClick.watchlist')
            return

        if C.CONTROL_RAIL_FIRST <= cid < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_DETAIL:
            self._open_selected(cid)

    def onAction(self, action):
        aid = action.getId()

        if aid in C.ACTION_BACK:
            self._close_current_window()
            return

        # Some remotes send SELECT but not onClick
        if aid in C.ACTION_SELECT:
            try:
                cid = self.getFocusId()
                if cid == C.CONTROL_BACK:
                    self._close_current_window()
                    return
                if (
                    C.CONTROL_RAIL_FIRST
                    <= cid
                    < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_DETAIL
                ):
                    if not self._is_duplicate_activation(cid):
                        self._open_selected(cid)
                    return
                # onClick performs duplicate protection for normal buttons.
                self.onClick(cid)
            except Exception:
                self._log_error('onAction.select')

    def _open_selected(self, cid):
        try:
            item = self.getControl(cid).getSelectedItem()
        except RuntimeError:
            return
        if not item:
            return

        p = C.PROP_PREFIX
        kind = item.getProperty('{}.kind'.format(p))
        deeplink_id = item.getProperty('{}.deeplink_id'.format(p))
        show_id = item.getProperty('{}.show_id'.format(p))
        season_id = item.getProperty('{}.season_id'.format(p))
        browse_id = item.getProperty('{}.browse_id'.format(p))
        open_path = item.getProperty('{}.open_path'.format(p))
        pp = item.getProperty('{}.play_path'.format(p))

        # Episode/video: play directo
        if kind in (C.KIND_EPISODE, C.KIND_VIDEO) and pp:
            self._play(pp)
            return

        # Movie: open detail via controller
        if kind == C.KIND_MOVIE and deeplink_id:
            self.controller.open_movie(deeplink_id)
            return

        # Show: open detail
        if kind == C.KIND_SHOW and show_id:
            self.controller.open_show(show_id)
            return

        # Season: open detail
        if kind == C.KIND_SEASON and show_id and season_id:
            self.controller.open_season(show_id, season_id)
            return

        # Collection/brand page: keep navigation inside Clean UI.
        if browse_id and self.controller:
            self.controller.open_collection(
                browse_id,
                item.getLabel() or '',
            )
            return

        # Fallback: play
        if pp:
            self._play(pp)
            return

        # Keep the plugin fallback already used by HomeWindow.
        if open_path:
            xbmc.executebuiltin(
                'RunPlugin("{}")'.format(open_path.replace('"', '\\"'))
            )

    def _play(self, path):
        if not path:
            return
        self.controller.play(path)

    def release_resources(self):
        """Libera referencias a ListItem y texturas al cerrar la ventana.

        No borra self.screen: la pila de restauración lo necesita para
        reconstruir la pantalla tras la reproducción (la posición del foco
        se conserva en screen._cleanui_window_state).
        """
        prefix = C.PROP_PREFIX
        for index in range(C.MAX_RAILS_DETAIL):
            try:
                self.getControl(
                    C.CONTROL_RAIL_FIRST + index
                ).reset()
            except Exception:
                pass
        for name in (
            'detail.title',
            'detail.fanart',
            'detail.poster',
            'detail.logo',
            'detail.plot',
            'detail.play_path',
            'detail.trailer_path',
            'detail.watchlist_action',
            'detail.kind',
            'detail.meta',
            'detail.genre',
        ):
            self.setProperty(
                '{}.{}'.format(prefix, name),
                '',
            )
