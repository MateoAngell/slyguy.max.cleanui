import time
import traceback

import xbmc
import xbmcgui

from . import constants as C
from .adapter import UIAdapter
from slyguy import userdata


class HomeWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *a, **kw):
        self.controller = kw.pop('controller', None)
        self.screen = kw.pop('screen', None)
        self.screen_kind = kw.pop('screen_kind', 'home')
        super(HomeWindow, self).__init__(*a, **kw)
        self._last_focus_key = None
        self._last_activation = None
        self._menu_block_until = 0
        self._profile_block_until = 0

    def onInit(self):
        # La cortina la retira el controlador vía onFocus() (handshake de foco),
        # no aquí: retirarla en onInit dejaría la ventana de Vídeos expuesta
        # durante los frames en que la nueva ventana aún no se compone.
        try:
            self._populate()
            if not self._restore_state():
                self._focus_first()
            # Debe reiniciarse también después de restaurar el foco.
            self._last_focus_key = None
            self._refresh_hero_from_focus()
        except Exception:
            self._log_error('onInit')
            if self.controller:
                self.controller.end_transition()
            try:
                self.close()
            except Exception:
                pass

    def replace_screen(self, screen, screen_kind=None):
        """Replace the current Home-like screen without opening another dialog."""
        if not screen:
            return False
        xbmc.log(
            '[CLEANUI] Reemplazando pantalla Home-like: '
            'perfil={!r} tipo={}'.format(
                userdata.get('profile', '') or '',
                getattr(screen, 'screen_type', 'unknown'),
            ),
            xbmc.LOGINFO,
        )
        self.screen = screen
        if screen_kind is not None:
            self.screen_kind = screen_kind
        self._last_focus_key = None
        self._last_activation = None
        self._populate()
        xbmc.sleep(80)
        try:
            self.setFocus(self.getControl(C.CONTROL_PROFILE))
        except RuntimeError:
            self._focus_first()
        self._last_focus_key = None
        self._refresh_hero_from_focus()
        return True

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

        for index in range(C.MAX_RAILS_HOME):
            control_id = self._rail_control_id(index)
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
            '[CLEANUI] Estado de Home guardado: foco={}, posiciones={}'.format(
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
                (
                    C.CONTROL_RAIL_FIRST
                    <= focus_id
                    < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_HOME
                    or focus_id == 4101
                )
                and control.size() <= 0
            ):
                return False
            self.setFocus(control)
            xbmc.log(
                '[CLEANUI] Estado de Home restaurado: foco={}, '
                'posiciones={}'.format(
                    focus_id,
                    positions,
                ),
                xbmc.LOGINFO,
            )
            return True
        except Exception:
            xbmc.log(
                '[CLEANUI] No se pudo restaurar el foco exacto de Home',
                xbmc.LOGWARNING,
            )
            return False

    def _log_error(self, context):
        xbmc.log(
            '[CLEANUI] HomeWindow.{}:\n{}'.format(
                context,
                traceback.format_exc(),
            ),
            xbmc.LOGERROR,
        )

    def _rail_control_id(self, rail_index):
        """Return the correct control ID for a rail index.

        Rail index 1 uses 4101 instead of 4001 for Movies/Series/Collection
        screens (which need poster layout). Home keeps 4001 (landscape for
        Continue Watching).
        """
        if rail_index == 1 and self.screen_kind != 'home':
            return 4101
        return C.CONTROL_RAIL_FIRST + rail_index

    def _populate(self):
        prefix = C.PROP_PREFIX

        previous_fanart = self.getProperty(
            '{}.hero.fanart'.format(prefix)
        ) or ''
        for property_name in (
            'title',
            'poster',
            'plot',
            'meta',
        ):
            self.setProperty(
                '{}.hero.{}'.format(prefix, property_name),
                '',
            )
        # Conservar el fondo hasta que _set_hero_from_card() tenga preparado
        # el nuevo. Evita descubrir la ventana padre durante la sustitución.
        if not previous_fanart:
            self.setProperty(
                '{}.hero.fanart'.format(prefix),
                '',
            )

        profile_data = userdata.get('profile') or {}
        profile_avatar = profile_data.get('avatar', '') or ''
        profile_name = profile_data.get('name', '') or ''
        self.setProperty(
            '{}.profile.avatar'.format(prefix),
            profile_avatar,
        )
        self.setProperty(
            '{}.profile.name'.format(prefix),
            profile_name,
        )
        self.setProperty(
            '{}.profile.has_avatar'.format(prefix),
            'true' if profile_avatar else 'false',
        )

        self.setProperty(
            '{}.screen.kind'.format(prefix),
            self.screen_kind,
        )

        for index in range(C.MAX_RAILS_HOME):
            self.setProperty(
                '{}.home.rail{}.title'.format(prefix, index),
                '',
            )
            self.setProperty(
                '{}.home.rail{}.visible'.format(prefix, index),
                'false',
            )
            self.setProperty(
                '{}.home.rail{}.style'.format(prefix, index),
                '',
            )

            try:
                self.getControl(
                    C.CONTROL_RAIL_FIRST + index
                ).reset()
            except RuntimeError:
                pass

        # 4101 sustituye a 4001 fuera de Home.
        try:
            self.getControl(4101).reset()
        except RuntimeError:
            pass

        if not self.screen:
            return

        if self.screen.hero:
            self._set_hero_from_card(self.screen.hero)

        for index, rail in enumerate(
            self.screen.rails[:C.MAX_RAILS_HOME]
        ):
            if not rail or not rail.items:
                continue

            control_id = self._rail_control_id(index)

            try:
                control = self.getControl(control_id)
            except RuntimeError:
                xbmc.log(
                    '[CLEANUI] No existe el control Home {}'.format(
                        control_id
                    ),
                    xbmc.LOGWARNING,
                )
                continue

            effective_style = UIAdapter._effective_rail_style(
                rail, self.screen_kind
            )

            list_items = []
            inserted_cards = []
            failed = 0
            first_error = None

            for card in rail.items:
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

            if not list_items:
                xbmc.log(
                    '[CLEANUI] Rail Home descartado: indice={} '
                    'titulo={!r} estilo={} sin tarjetas validas'.format(
                        index,
                        rail.title,
                        rail.style,
                    ),
                    xbmc.LOGWARNING,
                )
                continue

            try:
                control.addItems(list_items)
            except Exception:
                self._log_error('populate.addItems')
                continue

            # Debe conservarse: sincroniza el modelo con lo realmente insertado.
            rail.items = inserted_cards

            if failed:
                xbmc.log(
                    '[CLEANUI] Rail {!r}: {} tarjetas fallaron al '
                    'convertir. Primer error:\n{}'.format(
                        rail.title,
                        failed,
                        first_error,
                    ),
                    xbmc.LOGERROR,
                )

            self.setProperty(
                '{}.home.rail{}.title'.format(prefix, index),
                rail.title or '',
            )
            self.setProperty(
                '{}.home.rail{}.style'.format(prefix, index),
                rail.style or '',
            )
            self.setProperty(
                '{}.home.rail{}.visible'.format(prefix, index),
                'true',
            )

            xbmc.log(
                '[CLEANUI] Rail Home preparado: indice={} id={} '
                'titulo={!r} estilo={} tarjetas={}'.format(
                    index,
                    rail.rail_id,
                    rail.title,
                    rail.style,
                    len(inserted_cards),
                ),
                xbmc.LOGDEBUG,
            )

    def _focus_first(self):
        if not self.screen:
            return
        for index in range(
            min(len(self.screen.rails), C.MAX_RAILS_HOME)
        ):
            control_id = self._rail_control_id(index)
            try:
                control = self.getControl(control_id)
                if control.size() <= 0:
                    continue
                control.selectItem(0)
                self.setFocus(control)
                return
            except RuntimeError:
                continue
        try:
            self.setFocus(self.getControl(C.CONTROL_MENU))
        except RuntimeError:
            pass

    def _selected_card(self, control_id=None):
        if not self.screen:
            return None

        if control_id is None:
            try:
                control_id = self.getFocusId()
            except Exception:
                return None

        # Map 4101 (Movies/Series poster rail) to rail_index 1
        if control_id == 4101:
            rail_index = 1
        else:
            rail_index = control_id - C.CONTROL_RAIL_FIRST

        if rail_index < 0 or rail_index >= len(self.screen.rails):
            return None

        rail = self.screen.rails[rail_index]

        try:
            position = self.getControl(
                control_id
            ).getSelectedPosition()
        except Exception:
            return None

        if position < 0 or position >= len(rail.items):
            return None

        return rail.items[position]

    def _refresh_hero_from_focus(self):
        try:
            control_id = self.getFocusId()
        except Exception:
            return

        card = self._selected_card(control_id)
        if not card:
            return

        try:
            position = self.getControl(
                control_id
            ).getSelectedPosition()
        except Exception:
            return

        key = (control_id, position)

        if key == self._last_focus_key:
            return

        self._last_focus_key = key
        self._set_hero_from_card(card)

    def _set_hero_from_card(self, card):
        prefix = C.PROP_PREFIX
        art = card.art or {}
        info = card.info or {}

        self.setProperty(
            '{}.hero.title'.format(prefix),
            card.label or '',
        )
        fanart = (
            art.get('fanart')
            or art.get('fanart1')
            or art.get('banner')
            or art.get('thumb')
            or art.get('keyart')
            or art.get('poster')
            or ''
        )
        # Algunas tarjetas no incluyen fondo propio. No dejar el fondo vacío
        # porque una ventana modal transparente puede mostrar la pantalla
        # padre con sus rails como si fuese una imagen estática.
        if not fanart and self.screen and self.screen.hero:
            fallback_art = self.screen.hero.art or {}
            fanart = (
                fallback_art.get('fanart')
                or fallback_art.get('fanart1')
                or fallback_art.get('banner')
                or fallback_art.get('thumb')
                or fallback_art.get('keyart')
                or fallback_art.get('poster')
                or ''
            )
        # Si la pantalla ya tiene un fondo válido, conservarlo antes que
        # establecer una textura vacía.
        if not fanart:
            fanart = self.getProperty(
                '{}.hero.fanart'.format(prefix)
            ) or ''
        self.setProperty(
            '{}.hero.fanart'.format(prefix),
            fanart,
        )
        self.setProperty(
            '{}.hero.poster'.format(prefix),
            art.get('poster')
            or art.get('keyart')
            or art.get('thumb')
            or '',
        )
        self.setProperty(
            '{}.hero.plot'.format(prefix),
            info.get('plot') or '',
        )

        metadata = []

        year = info.get('year')
        if year:
            metadata.append(str(year))

        rating = info.get('rating') or info.get('mpaa')
        if rating:
            metadata.append(str(rating))

        try:
            duration = max(0, int(info.get('duration') or 0))
        except (TypeError, ValueError):
            duration = 0
        if duration:
            minutes = duration // 60
            hours, minutes = divmod(minutes, 60)

            if hours:
                metadata.append('{}h {}m'.format(hours, minutes))
            else:
                metadata.append('{}m'.format(minutes))

        genre = info.get('genre')

        if isinstance(genre, (list, tuple)):
            genre = ', '.join(str(value) for value in genre)

        if genre:
            metadata.append(str(genre))

        self.setProperty(
            '{}.hero.meta'.format(prefix),
            '  •  '.join(metadata),
        )

    def _is_duplicate_activation(self, control_id):
        try:
            position = self.getControl(
                control_id
            ).getSelectedPosition()
        except Exception:
            position = -1

        key = (control_id, position)
        now = time.monotonic()

        if self._last_activation:
            previous_key, previous_time = self._last_activation

            if (
                previous_key == key
                and now - previous_time < 0.6
            ):
                return True

        self._last_activation = (key, now)
        return False

    def onFocus(self, control_id):
        # Handshake de transición: la ventana recuperó el foco; el controlador
        # puede retirar la cortina si esta ventana era el destino de la
        # transición (evita parpadeo al volver de una hija o tras reproducción).
        if self.controller:
            self.controller.notify_window_focused(self)
        self._refresh_hero_from_focus()

    def onClick(self, control_id):
        if (
            C.CONTROL_RAIL_FIRST
            <= control_id
            < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_HOME
            or control_id == 4101
        ):
            self._last_focus_key = None
            self._refresh_hero_from_focus()
        self._activate_control(control_id)

    def _refresh_hero_for_horizontal_action(self, action_id):
        """
        Actualiza el hero al moverse dentro del mismo rail.
        Kodi no siempre llama a onFocus() cuando solamente cambia la posición
        seleccionada de un contenedor. Este método no mueve el control: la
        navegación continúa siendo responsabilidad exclusiva del XML.
        """
        if not self.screen:
            return
        try:
            control_id = self.getFocusId()
        except Exception:
            return
        if not (
            C.CONTROL_RAIL_FIRST
            <= control_id
            < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_HOME
            or control_id == 4101
        ):
            return
        if control_id == 4101:
            rail_index = 1
        else:
            rail_index = control_id - C.CONTROL_RAIL_FIRST
        if rail_index < 0 or rail_index >= len(self.screen.rails):
            return
        rail = self.screen.rails[rail_index]
        if not rail or not rail.items:
            return
        try:
            position = self.getControl(
                control_id
            ).getSelectedPosition()
        except Exception:
            return
        target_position = position
        if action_id in C.ACTION_LEFT:
            target_position = position - 1
        elif action_id in C.ACTION_RIGHT:
            target_position = position + 1
        else:
            return
        target_position = max(
            0,
            min(target_position, len(rail.items) - 1),
        )
        if target_position < 0 or target_position >= len(rail.items):
            return
        self._last_focus_key = (control_id, target_position)
        self._set_hero_from_card(rail.items[target_position])

    def onAction(self, action):
        action_id = action.getId()

        if action_id in C.ACTION_BACK:
            if (
                self.screen_kind == C.SCREEN_HOME
                and self.controller
            ):
                self.controller.exit_clean_ui()
            elif self.controller and self.controller._home_stack:
                # BACK desde una seccion hermana: recargar la seccion anterior
                # (reutiliza la ventana, no apila). Vease _open_home_like().
                prev, prev_kind = self.controller._home_stack.pop()
                try:
                    self.replace_screen(prev, prev_kind)
                except Exception:
                    self._log_error('back_replace')
                return
            elif self.controller:
                self.controller.close_child_window(self)
            else:
                self.close()
            return

        if (
            action_id in C.ACTION_LEFT
            or action_id in C.ACTION_RIGHT
        ):
            self._refresh_hero_for_horizontal_action(action_id)

        if action_id in C.ACTION_MENU:
            self._activate_control(C.CONTROL_MENU)
            return

        if action_id in C.ACTION_SELECT:
            try:
                self._activate_control(self.getFocusId())
            except Exception:
                self._log_error('onAction.select')
            return

    def _activate_control(self, control_id):
        if control_id == C.CONTROL_PROFILE:
            now = time.monotonic()
            if now < self._profile_block_until:
                return
            if self._is_duplicate_activation(control_id):
                return
            # El selector es modal. Algunos mandos vuelven a entregar el SELECT
            # usado para confirmar el perfil cuando Home recupera el control.
            self._profile_block_until = now + 1.0
            try:
                if self.controller:
                    self.controller.select_profile(self)
            finally:
                # Bloquear tanto el onClick tardío como el SELECT residual.
                finished_at = time.monotonic()
                self._profile_block_until = finished_at + 1.0
                self._last_activation = (
                    (C.CONTROL_PROFILE, -1),
                    finished_at,
                )
            return

        if control_id == C.CONTROL_MOVIES:
            if self._is_duplicate_activation(control_id):
                return
            if self.controller:
                self.controller.open_movies(self)
            return

        if control_id == C.CONTROL_SERIES:
            if self._is_duplicate_activation(control_id):
                return
            if self.controller:
                self.controller.open_series(self)
            return

        if control_id == C.CONTROL_MENU:
            now = time.monotonic()
            if now < self._menu_block_until:
                return
            if self._is_duplicate_activation(control_id):
                return
            # Bloquear eventos SELECT/onClick que lleguen mientras el
            # diálogo está abierto.
            self._menu_block_until = now + 0.75
            try:
                self._open_menu()
            finally:
                # Algunos mandos entregan el segundo evento justo después
                # de cerrar Dialog.select().
                self._menu_block_until = time.monotonic() + 0.75
                self._last_activation = (
                    (C.CONTROL_MENU, -1),
                    time.monotonic(),
                )
            return

        if not (
            C.CONTROL_RAIL_FIRST
            <= control_id
            < C.CONTROL_RAIL_FIRST + C.MAX_RAILS_HOME
            or control_id == 4101
        ):
            return

        if self._is_duplicate_activation(control_id):
            return

        card = self._selected_card(control_id)

        if not card:
            return

        xbmc.log(
            '[CLEANUI] Activando Home: kind={} label={} '
            'deeplink={} show={} season={}'.format(
                card.kind,
                card.label,
                card.deeplink_id,
                card.show_id,
                card.season_id,
            ),
            xbmc.LOGINFO,
        )

        try:
            if card.kind in (C.KIND_EPISODE, C.KIND_VIDEO):
                self._play(card.play_path)
                return

            if (
                card.kind == C.KIND_MOVIE
                and card.deeplink_id
                and self.controller
            ):
                self.controller.open_movie(card.deeplink_id)
                return

            if (
                card.kind == C.KIND_SHOW
                and card.show_id
                and self.controller
            ):
                self.controller.open_show(card.show_id)
                return

            if (
                card.browse_id
                and self.controller
            ):
                self.controller.open_collection(
                    card.browse_id,
                    card.label,
                    self,
                )
                return

            if (
                card.kind == C.KIND_SEASON
                and card.show_id
                and card.season_id
                and self.controller
            ):
                self.controller.open_season(
                    card.show_id,
                    card.season_id,
                )
                return

            if card.open_path:
                safe_path = card.open_path.replace('"', '\\"')
                xbmc.executebuiltin(
                    'RunPlugin("{}")'.format(safe_path)
                )
                return

            if card.play_path:
                self._play(card.play_path)
                return

            xbmcgui.Dialog().notification(
                'HBO Max Clean UI',
                'Este elemento no tiene una acción disponible',
                xbmcgui.NOTIFICATION_WARNING,
                3000,
            )

        except Exception:
            self._log_error('activate')
            xbmcgui.Dialog().ok(
                'HBO Max Clean UI',
                'No se pudo abrir "{}".\n\n'
                'Revisa kodi.log.'.format(card.label),
            )

    def _play(self, path):
        if not path:
            return

        if self.controller:
            self.controller.play(path)
            return

        self.close()
        xbmc.sleep(250)
        xbmc.executebuiltin(
            'PlayMedia("{}",0)'.format(
                path.replace('"', '\\"')
            )
        )

    def _open_menu(self):
        options = [
            'Buscar',
            'Mi lista',
            'Continuar viendo',
            'Ajustes',
            'Cerrar sesión',
        ]

        choice = xbmcgui.Dialog().select(
            'Menú de HBO Max',
            options,
        )

        if choice < 0:
            return

        import resources.lib.plugin as core

        if choice == 0:
            if self.controller:
                self.controller.open_search()
            return

        if choice == 1:
            if self.controller:
                self.controller.open_watchlist(self)
            return

        if choice == 2:
            if self.controller:
                self.controller.open_continue_watching(self)
            return

        if choice == 3:
            xbmc.executebuiltin(
                'Addon.OpenSettings(slyguy.max.cleanui)'
            )
            return

        if choice == 4:
            path = core.plugin.url_for(core.logout)
            if self.controller:
                self.controller.run_plugin_after_close(path)
            else:
                xbmc.executebuiltin(
                    'RunPlugin("{}")'.format(
                        path.replace('"', '\\"')
                    )
                )

    def release_resources(self):
        """Libera referencias a ListItem y texturas al cerrar la ventana.

        No borra self.screen: la pila de restauración lo necesita para
        reconstruir la pantalla tras la reproducción (la posición del foco
        se conserva en screen._cleanui_window_state).
        """
        prefix = C.PROP_PREFIX
        for index in range(C.MAX_RAILS_HOME):
            try:
                self.getControl(
                    C.CONTROL_RAIL_FIRST + index
                ).reset()
            except Exception:
                pass
        try:
            self.getControl(4101).reset()
        except Exception:
            pass
        for name in (
            'hero.title',
            'hero.fanart',
            'hero.poster',
            'hero.plot',
            'hero.meta',
            'profile.avatar',
        ):
            self.setProperty(
                '{}.{}'.format(prefix, name),
                '',
            )
