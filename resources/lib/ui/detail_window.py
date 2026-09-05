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
            self._configure_navigation()
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
            # Visibility conditions are evaluated by Kodi's render loop.
            # Use the populated model here, including actions that may have
            # disappeared since this screen was last open.
            if focus_id not in self._rail_ids() + self._action_ids():
                return False
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
        selected = getattr(self.screen, 'selected_season', None)
        self.setProperty('cleanui.detail.season_label', selected.label if selected else '')
        self.setProperty('cleanui.detail.play_label', getattr(self.screen, 'play_label', 'Reproducir'))
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
            if ('watchlist' in s or 'lista' in s or 'guardar' in s
                    or 'add_watchlist' in act or 'delete_watchlist' in act):
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
            style_property = '{}.detail.rail{}.style'.format(p, i)
            self.setProperty(style_property, '')

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
            self.setProperty(style_property, effective_style)
            # Collapse wide rows to their actual content height. Hidden
            # groups are also removed from the XML grouplist's layout.
            wide = effective_style in (
                C.STYLE_LANDSCAPE, C.STYLE_EPISODE, C.STYLE_BRAND,
            )
            try:
                control.setHeight(280 if wide else 328)
                self.getControl(6000 + i).setHeight(320 if wide else 368)
            except (RuntimeError, AttributeError):
                # Older custom skins can omit the sizing group IDs.
                pass

    def _rail_ids(self):
        """Return populated rails without waiting for render visibility."""
        result = []
        for i in range(C.MAX_RAILS_DETAIL):
            cid = C.CONTROL_RAIL_FIRST + i
            if self.getProperty('{}.detail.rail{}.visible'.format(
                    C.PROP_PREFIX, i)) != 'true':
                continue
            try:
                if self.getControl(cid).size() > 0:
                    result.append(cid)
            except RuntimeError:
                continue
        return result

    def _action_ids(self):
        result = [C.CONTROL_BACK]
        for name, cid in (
            ('play_path', C.CONTROL_PLAY),
            ('trailer_path', C.CONTROL_TRAILER),
            ('watchlist_action', C.CONTROL_WATCHLIST),
            ('season_label', 1004),
        ):
            if self.getProperty('{}.detail.{}'.format(C.PROP_PREFIX, name)):
                result.append(cid)
        return result

    def _configure_navigation(self):
        """Connect real actions and populated rails, skipping empty slots.

        Kodi handles directional input before Python onAction. Set native
        navigation targets once, rather than moving focus a second time in
        the action callback or relying on still-pending visibility rules.
        """
        rails = self._rail_ids()
        actions = self._action_ids()
        self._sync_native_visibility(rails, actions)
        primary = next((cid for cid in actions if cid != C.CONTROL_BACK),
                       C.CONTROL_BACK)
        for index, cid in enumerate(actions):
            control = self.getControl(cid)
            control.controlLeft(self.getControl(actions[max(0, index - 1)]))
            control.controlRight(self.getControl(actions[min(len(actions) - 1, index + 1)]))
            control.controlUp(control)
            control.controlDown(self.getControl(rails[0]) if rails else control)
        for index, cid in enumerate(rails):
            control = self.getControl(cid)
            control.controlUp(self.getControl(rails[index - 1] if index else primary))
            control.controlDown(self.getControl(rails[min(len(rails) - 1, index + 1)]))

    def _sync_native_visibility(self, rails, actions):
        """Make populated controls focusable before Kodi's first render.

        setFocus queues GUI_MSG_SETFOCUS; Kodi rejects that message if the
        destination's native visibility still reflects the previous frame.
        setVisible alone only changes forceHidden. A literal visibility
        condition also updates the native visible state synchronously.
        Restore the XML expression afterwards so later property changes
        continue to control visibility, including reused/empty page slots.
        """
        def sync(cid, visible, condition):
            control = self.getControl(cid)
            # Clear a stale forceHidden override; m_visible below supplies
            # the immediate state and the expression owns future frames.
            control.setVisible(True)
            control.setVisibleCondition('true' if visible else 'false')
            control.setVisibleCondition(condition)

        for i in range(C.MAX_RAILS_DETAIL):
            cid = C.CONTROL_RAIL_FIRST + i
            condition = 'String.IsEqual(Window.Property({}.detail.rail{}.visible),true)'.format(
                C.PROP_PREFIX, i)
            sync(cid, cid in rails, condition)
            try:
                sync(6000 + i, cid in rails, condition)
            except RuntimeError:
                # Compatibility with a custom skin lacking sizing groups.
                pass
        sync(C.CONTROL_BACK, True, 'true')
        for name, cid in (
            ('play_path', C.CONTROL_PLAY),
            ('trailer_path', C.CONTROL_TRAILER),
            ('watchlist_action', C.CONTROL_WATCHLIST),
            ('season_label', 1004),
        ):
            condition = '!String.IsEmpty(Window.Property({}.detail.{}))'.format(
                C.PROP_PREFIX, name)
            sync(cid, cid in actions, condition)

    def _focus_best(self):
        """Focus seasons/episodes for a series, or Play for a movie.

        isVisible() can still be false during onInit after setting the XML
        properties, although the rail has already been populated.
        """
        rails = self._rail_ids()
        actions = self._action_ids()
        buttons = [cid for cid in actions if cid != C.CONTROL_BACK]
        if self.screen.screen_type == C.SCREEN_MOVIE:
            candidates = buttons + rails
        else:
            candidates = rails + buttons
        for control_id in candidates + [C.CONTROL_BACK]:
            try:
                control = self.getControl(control_id)
                if control_id in rails and control.getSelectedPosition() < 0:
                    control.selectItem(0)
                self.setFocus(control)
                return
            except RuntimeError:
                continue

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
        if getattr(self, '_page_history', None):
            self.screen = self._page_history.pop()
            self.onInit()
            return
        if self.controller:
            self.controller.close_child_window(self)
        else:
            self.close()

    def onClick(self, cid):
        if cid == 1004:
            seasons = getattr(self.screen, 'season_choices', [])
            if not seasons or not self.controller:
                return
            from .choice_window import choose
            index = choose(self.controller.addon_path, 'Temporadas', [card.label for card in seasons])
            if index >= 0:
                try:
                    self.controller.switch_season(self, seasons[index])
                except Exception:
                    self._log_error('switch_season')
                    xbmcgui.Dialog().ok('HBO Max', 'No se pudo cargar esta temporada. Inténtalo de nuevo.')
            return
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

        # WindowXML delivers native button/list activation through onClick
        # before its Python onAction callback. Opening a child can take long
        # enough to outlive the click debounce, so handling SELECT here too
        # can open the same season twice or pop two pages on Back.

    def _open_selected(self, cid):
        try:
            position = self.getControl(cid).getSelectedPosition()
            cards = self.screen.rails[cid - C.CONTROL_RAIL_FIRST].items
            if position < 0 or position >= len(cards):
                return
            card = cards[position]
            if card.kind == 'page' and self.controller:
                self.controller.open_next_page(card, self)
                return
        except (IndexError, RuntimeError):
            return
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
            self.controller.open_movie(deeplink_id, card)
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
