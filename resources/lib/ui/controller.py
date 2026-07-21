import time
import traceback

import xbmc
import xbmcaddon
import xbmcgui

from slyguy import gui

from .repository import Repository
from .home_window import HomeWindow
from .detail_window import DetailWindow


class PerfTimer(object):
    """Medidor ligero de rendimiento (logs a LOGDEBUG, sin coste visible)."""

    def __init__(self, name):
        self.name = name
        self.started = time.monotonic()

    def mark(self, stage):
        elapsed = (time.monotonic() - self.started) * 1000.0
        xbmc.log(
            '[CLEANUI][PERF] {} {}: {:.1f} ms'.format(
                self.name,
                stage,
                elapsed,
            ),
            xbmc.LOGDEBUG,
        )
        return elapsed


class _TransitionCurtain(xbmcgui.WindowDialog):
    """Oculta brevemente la interfaz nativa de Kodi entre ventanas."""

    def __init__(self):
        super(_TransitionCurtain, self).__init__()
        self._background = xbmcgui.ControlImage(
            0,
            0,
            1920,
            1080,
            'white.png',
            colorDiffuse='FF000000',
        )
        self.addControl(self._background)


class UIController(object):
    def __init__(self):
        self.repository = Repository()
        self.addon_path = xbmcaddon.Addon().getAddonInfo('path')
        self._windows = []
        # Pila de modelos Screen para secciones hermanas (Home/Peliculas/Series/...).
        # Solo guarda datos (no ventanas Kodi) para que BACK recargue la seccion
        # anterior sin apilar WindowXMLDialog. Vease _open_home_like().
        self._home_stack = []
        self._pending_playback = None
        self._pending_builtin = None
        self._processing_playback = False
        self._restored_stack = None
        self._selecting_profile = False
        # True únicamente cuando el usuario solicita salir desde el Home.
        self.exit_requested = False
        self._transition_curtain = None
        self._closing_all_windows = False
        self._quit_issued = False
        self._transition_release_target = None

    def _show_error(self, context):
        error = traceback.format_exc()

        xbmc.log(
            '[CLEANUI] UIController.{}:\n{}'.format(context, error),
            xbmc.LOGERROR,
        )

        xbmcgui.Dialog().ok(
            'Disney+ Clean UI',
            'No se pudo abrir esta pantalla.\n\n'
            'Revisa kodi.log y busca [CLEANUI].',
        )

    def begin_transition(self):
        """Cubre la interfaz nativa de Kodi durante una transición."""
        if self._transition_curtain is not None:
            return
        try:
            curtain = _TransitionCurtain()
            self._transition_curtain = curtain
            curtain.show()
            xbmc.sleep(30)
        except Exception:
            self._transition_curtain = None
            xbmc.log(
                '[CLEANUI] No se pudo mostrar la cortina de transición:\n'
                '{}'.format(traceback.format_exc()),
                xbmc.LOGWARNING,
            )

    def end_transition(self):
        """Retira la cortina cuando la siguiente interfaz ya está preparada."""
        curtain = self._transition_curtain
        self._transition_curtain = None
        if curtain is None:
            return
        try:
            curtain.close()
        except Exception:
            xbmc.log(
                '[CLEANUI] No se pudo cerrar la cortina de transición:\n'
                '{}'.format(traceback.format_exc()),
                xbmc.LOGWARNING,
            )

    def _finish_exit_if_ready(self):
        """
        Sale del addon (a la home de Kodi) únicamente cuando ya no queda ningún
        WindowDialog Clean UI dentro de doModal(). NO cierra Kodi.
        """
        if not self.exit_requested:
            return False
        if self._windows:
            return False
        if self._quit_issued:
            return True
        self._quit_issued = True
        self._closing_all_windows = False
        self._transition_release_target = None
        # Todos los WindowXMLDialog Clean UI ya abandonaron doModal(). La ventana
        # activa subyacente es Videos (host del pluginsource). ReplaceWindow
        # sustituye ese host en la pila en vez de dejarlo debajo de Home, evitando
        # que quede visible el directorio del plugin ("Abrir Disney Clean UI").
        self.end_transition()
        xbmc.log(
            '[CLEANUI] Todas las ventanas Clean UI terminaron; '
            'reemplazando Videos por Home',
            xbmc.LOGINFO,
        )
        try:
            xbmc.executebuiltin('ReplaceWindow(Home)')
        except Exception:
            xbmc.log(
                '[CLEANUI] Error reemplazando Videos por Home:\n{}'.format(
                    traceback.format_exc()
                ),
                xbmc.LOGERROR,
            )
        return True

    def notify_window_focused(self, window):
        """
        Recibe la confirmación de Kodi de que una ventana Clean UI ha
        recuperado el foco. Si esa ventana era la que debía quedar expuesta
        tras una transición, ya se puede retirar la cortina. No usa sleep fijo
        ni polling de getFocusId().
        """
        if self.exit_requested or self._closing_all_windows:
            return
        if self._transition_curtain is None:
            return
        if self._transition_release_target is not window:
            return
        # Durante una reconstrucción de la pila tras reproducción, todavía
        # puede faltar por restaurar una pantalla padre. No descubrir Videos
        # entre una restauración y la siguiente.
        if (
            self._processing_playback
            and self._restored_stack
            and len(self._restored_stack) > 1
        ):
            return
        self._transition_release_target = None
        xbmc.log(
            '[CLEANUI] Ventana padre recuperó foco; retirando cortina',
            xbmc.LOGINFO,
        )
        self.end_transition()

    def close_child_window(self, window):
        """
        Cierra una pantalla secundaria ocultando el salto momentáneo a la
        ventana de vídeos de Kodi.
        """
        if window not in self._windows:
            try:
                window.close()
            except Exception:
                pass
            return

        # Regreso normal a una ventana ya apilada (padre Clean UI vivo debajo):
        # no mostrar cortina negra, porque revelaría la ventana de Vídeos y
        # produciría el flash negro. Kodi revela al padre directamente.
        if len(self._windows) > 1 and not self._processing_playback:
            try:
                window.close()
            except Exception:
                xbmc.log(
                    '[CLEANUI] Error cerrando una ventana secundaria:\n'
                    '{}'.format(traceback.format_exc()),
                    xbmc.LOGERROR,
                )
            return

        # Casos sin superficie Clean UI estable debajo (vuelta desde
        # reproducción, reconstrucción de pila, navegación pendiente): sí usar
        # cortina. Armar el padre como destino de liberación ANTES de cerrar la
        # hija, para no depender del retorno de doModal().
        if len(self._windows) > 1:
            self._transition_release_target = self._windows[-2]
        self.begin_transition()
        try:
            window.close()
        except Exception:
            xbmc.log(
                '[CLEANUI] Error cerrando una ventana secundaria:\n'
                '{}'.format(traceback.format_exc()),
                xbmc.LOGERROR,
            )

    def _show_window(self, window):
        self._windows.append(window)
        # En la última fase de restauración tras cerrar fullscreenvideo, la
        # nueva ventana será la superficie Clean UI que debe sustituir a la
        # cortina. Se libera al recibir su onFocus(), no por temporización.
        if (
            self._transition_curtain is not None
            and self._processing_playback
            and self._restored_stack
            and len(self._restored_stack) == 1
            and not self.exit_requested
        ):
            self._transition_release_target = window
            xbmc.log(
                '[CLEANUI] Ultima ventana de restauracion armada como '
                'destino de la transicion',
                xbmc.LOGINFO,
            )
        try:
            window.doModal()
        finally:
            release = getattr(window, 'release_resources', None)
            if callable(release):
                try:
                    release()
                except Exception:
                    xbmc.log(
                        '[CLEANUI] Error liberando recursos de la '
                        'ventana:\n{}'.format(traceback.format_exc()),
                        xbmc.LOGWARNING,
                    )
            if window in self._windows:
                self._windows.remove(window)
        # Este código está fuera del finally para no ocultar excepciones.
        if self._windows:
            # La hija terminó su doModal(), pero no se retira la cortina
            # todavía. Kodi debe devolver foco a la ventana padre; onFocus() de
            # esa ventana notificará al controlador y liberará la cortina sin
            # sleep fijo.
            if not self._closing_all_windows:
                self._transition_release_target = self._windows[-1]
                xbmc.log(
                    '[CLEANUI] Esperando foco de la ventana padre antes '
                    'de retirar la cortina',
                    xbmc.LOGINFO,
                )
            return
        self._closing_all_windows = False
        if self.exit_requested:
            self._pending_playback = None
            self._pending_builtin = None
            self._finish_exit_if_ready()
            return
        if (
            self._pending_playback
            and not self._processing_playback
            and not self._pending_builtin
        ):
            self._drain_pending_playback()
            return
        if self._pending_builtin:
            command = self._pending_builtin
            self._pending_builtin = None
            xbmc.log(
                '[CLEANUI] Todas las ventanas se cerraron; '
                'ejecutando navegacion pendiente: {}'.format(command),
                xbmc.LOGINFO,
            )
            try:
                xbmc.executebuiltin(command)
            except Exception:
                xbmc.log(
                    '[CLEANUI] Error ejecutando navegacion pendiente:\n'
                    '{}'.format(traceback.format_exc()),
                    xbmc.LOGERROR,
                )
            finally:
                self.end_transition()
            return
        # Durante la reconstrucción secuencial todavía queda una pantalla padre
        # por abrir. No descubrir la ventana nativa de Kodi entre ambas.
        restoring_parent = (
            self._processing_playback
            and self._restored_stack
            and len(self._restored_stack) > 1
        )
        if restoring_parent:
            xbmc.log(
                '[CLEANUI] Manteniendo transición hasta restaurar '
                'la pantalla anterior',
                xbmc.LOGINFO,
            )
            return
        self.end_transition()

    def _navigation_screens(self):
        actual_screens = []
        seen = set()
        for window in self._windows:
            screen = getattr(window, 'screen', None)
            if not screen:
                continue
            key = id(screen)
            if key in seen:
                continue
            seen.add(key)
            actual_screens.append(screen)

        if self._restored_stack:
            screens = []
            seen = set()
            for screen in self._restored_stack[:-1]:
                key = id(screen)
                if key in seen:
                    continue
                seen.add(key)
                screens.append(screen)
            for screen in actual_screens:
                key = id(screen)
                if key in seen:
                    continue
                seen.add(key)
                screens.append(screen)
            if not actual_screens:
                for screen in self._restored_stack:
                    key = id(screen)
                    if key in seen:
                        continue
                    seen.add(key)
                    screens.append(screen)
            return screens

        return actual_screens

    def _restore_screen(self, screen):
        if not screen:
            return
        if screen.screen_type in ('home', 'collection'):
            screen_kind = (
                screen.screen_kind
                or ('home' if screen.screen_type == 'home' else 'collection')
            )
            window = HomeWindow(
                'uihome.xml',
                self.addon_path,
                'Default',
                '1080i',
                controller=self,
                screen=screen,
                screen_kind=screen_kind,
            )
        else:
            window = DetailWindow(
                'ui_detail.xml',
                self.addon_path,
                'Default',
                '1080i',
                controller=self,
                screen=screen,
            )
        self._show_window(window)
        del window

    def play(self, path):
        if (
            not path
            or self.exit_requested
            or self._pending_builtin
            or self._pending_playback
            or self._closing_all_windows
        ):
            return False

        for window in list(self._windows):
            try:
                capture_state = getattr(window, 'capture_state', None)
                if capture_state:
                    capture_state()
            except Exception:
                xbmc.log(
                    '[CLEANUI] No se pudo guardar el estado de una ventana:\n'
                    '{}'.format(traceback.format_exc()),
                    xbmc.LOGWARNING,
                )

        screens = self._navigation_screens()
        screen_names = [
            getattr(screen, 'screen_type', 'unknown')
            for screen in screens
        ]

        xbmc.log(
            '[CLEANUI] Preparando reproduccion; pila guardada: {}'.format(
                ' -> '.join(screen_names) if screen_names else '(vacia)'
            ),
            xbmc.LOGINFO,
        )

        self._pending_playback = {
            'path': path,
            'screens': screens,
        }

        self.begin_transition()
        self._close_all_windows()
        return True

    def _close_all_windows(self):
        if not self._windows:
            return
        self._closing_all_windows = True
        for window in reversed(list(self._windows)):
            try:
                window.close()
            except Exception:
                xbmc.log(
                    '[CLEANUI] Error solicitando el cierre de una ventana:\n'
                    '{}'.format(traceback.format_exc()),
                    xbmc.LOGERROR,
                )

    def open_plugin_directory(self, path):
        if not path:
            return False
        safe_path = path.replace('"', '\\"')
        self._pending_builtin = (
            'ActivateWindow(Videos,"{}",return)'.format(safe_path)
        )
        xbmc.log(
            '[CLEANUI] Directorio pendiente despues de cerrar '
            'Clean UI: {}'.format(safe_path),
            xbmc.LOGINFO,
        )
        self._close_all_windows()
        return True

    def run_plugin_after_close(self, path):
        if not path:
            return False
        safe_path = path.replace('"', '\\"')
        self._pending_builtin = 'RunPlugin("{}")'.format(safe_path)
        xbmc.log(
            '[CLEANUI] Accion de plugin pendiente despues de '
            'cerrar Clean UI',
            xbmc.LOGINFO,
        )
        self._close_all_windows()
        return True

    def exit_clean_ui(self):
        """
        Solicita la salida. Quit se ejecuta posteriormente, una sola vez,
        cuando todos los WindowDialog ya han abandonado doModal().
        """
        if self.exit_requested:
            return True

        # Solo abrir la cortina si hay ventanas Clean UI que proteger. Si la
        # pila ya está vacía, no crear/cerrar un WindowDialog inútil (flash).
        if self._windows:
            self.begin_transition()
        self.exit_requested = True
        self._pending_playback = None
        self._pending_builtin = None
        # Al salir del addon la pila de secciones ya no sirve; liberar sus
        # modelos Screen para no retenerlos.
        self._home_stack = []
        xbmc.log(
            '[CLEANUI] Salida explícita solicitada; cerrando todas las ventanas',
            xbmc.LOGINFO,
        )
        self._close_all_windows()
        # Normalmente habrá una Home activa y _show_window() llegará después
        # al estado vacío. Esto cubre también la ruta excepcional en la que
        # no hubiera ya ningún diálogo en la pila.
        self._finish_exit_if_ready()
        return True

    def _player_is_playing(self, player):
        try:
            return player.isPlayingVideo() or player.isPlaying()
        except Exception:
            return False

    def _player_has_media(self):
        try:
            return (
                xbmc.getCondVisibility('Player.HasMedia')
                or xbmc.getCondVisibility('Player.HasVideo')
                or xbmc.getCondVisibility('Player.HasAudio')
            )
        except Exception:
            return False

    def _close_busy_dialogs(self, context='', write_log=False):
        if write_log:
            xbmc.log(
                '[CLEANUI] Cerrando dialogos de carga de Kodi ({})'.format(
                    context or 'sin contexto'
                ),
                xbmc.LOGINFO,
            )
        for dialog_name in (
            'busydialog',
            'busydialognocancel',
        ):
            try:
                xbmc.executebuiltin(
                    'Dialog.Close({},true)'.format(dialog_name)
                )
            except Exception:
                xbmc.log(
                    '[CLEANUI] No se pudo cerrar {}:\n{}'.format(
                        dialog_name,
                        traceback.format_exc(),
                    ),
                    xbmc.LOGWARNING,
                )

    def _busy_dialog_visible(self):
        try:
            return (
                xbmc.getCondVisibility('Window.IsVisible(busydialog)')
                or xbmc.getCondVisibility(
                    'Window.IsVisible(busydialognocancel)'
                )
            )
        except Exception:
            return False

    def _stop_player_safely(self, player, context=''):
        xbmc.log(
            '[CLEANUI] Deteniendo reproduccion de forma segura ({})'.format(
                context or 'sin contexto'
            ),
            xbmc.LOGINFO,
        )
        try:
            player.stop()
        except Exception:
            xbmc.log(
                '[CLEANUI] Error deteniendo el reproductor:\n{}'.format(
                    traceback.format_exc()
                ),
                xbmc.LOGERROR,
            )
        monitor = xbmc.Monitor()
        for unused in range(50):
            if monitor.abortRequested():
                break
            playing = self._player_is_playing(player)
            has_media = self._player_has_media()
            fullscreen_visible = xbmc.getCondVisibility(
                'Window.IsVisible(fullscreenvideo)'
            )
            if not playing and not has_media and not fullscreen_visible:
                break
            xbmc.sleep(100)

    def _run_player(self, path):
        player = xbmc.Player()
        monitor = xbmc.Monitor()
        safe_path = path.replace('"', '\\"')

        xbmc.log(
            '[CLEANUI] Todas las ventanas se cerraron; '
            'preparando reproduccion: {}'.format(safe_path),
            xbmc.LOGINFO,
        )

        playback_started = False

        try:
            xbmc.sleep(100)

            self._close_busy_dialogs(
                'antes de PlayMedia',
                write_log=False,
            )

            xbmc.log(
                '[CLEANUI] Ejecutando PlayMedia(plugin://...)',
                xbmc.LOGINFO,
            )

            xbmc.executebuiltin(
                'PlayMedia("{}",0)'.format(safe_path)
            )

            video_ready_ticks = 0
            first_video_tick = None
            fullscreen_ready = False
            fullscreen_attempts = 0
            next_fullscreen_attempt = 0

            for tick in range(600):
                if monitor.abortRequested():
                    return False

                try:
                    playing_video = player.isPlayingVideo()
                    playing = playing_video or player.isPlaying()
                except Exception:
                    playing_video = False
                    playing = False

                has_video = xbmc.getCondVisibility('Player.HasVideo')

                fullscreen_visible = xbmc.getCondVisibility(
                    'Window.IsVisible(fullscreenvideo)'
                )

                video_ready = playing_video or (playing and has_video)

                if video_ready:
                    video_ready_ticks += 1
                else:
                    video_ready_ticks = 0

                if video_ready and fullscreen_visible:
                    playback_started = True
                    fullscreen_ready = True
                    break

                if video_ready_ticks >= 3:
                    playback_started = True

                    if first_video_tick is None:
                        first_video_tick = tick
                        next_fullscreen_attempt = tick + 5
                        xbmc.log(
                            '[CLEANUI] Kodi confirma video real; '
                            'esperando fullscreenvideo',
                            xbmc.LOGINFO,
                        )

                    if (
                        not fullscreen_visible
                        and fullscreen_attempts < 2
                        and tick >= next_fullscreen_attempt
                    ):
                        fullscreen_attempts += 1
                        xbmc.log(
                            '[CLEANUI] Solicitando fullscreenvideo '
                            '(intento {}/2)'.format(fullscreen_attempts),
                            xbmc.LOGINFO,
                        )
                        xbmc.executebuiltin(
                            'ActivateWindow(fullscreenvideo)'
                        )
                        next_fullscreen_attempt = tick + 30

                if (
                    first_video_tick is not None
                    and tick - first_video_tick >= 120
                ):
                    xbmc.log(
                        '[CLEANUI] El video comenzo pero fullscreenvideo '
                        'no pudo hacerse visible',
                        xbmc.LOGWARNING,
                    )
                    break

                xbmc.sleep(100)

            if not fullscreen_ready:
                if (
                    self._player_is_playing(player)
                    or self._player_has_media()
                ):
                    self._stop_player_safely(
                        player,
                        'fullscreenvideo no disponible durante el arranque',
                    )
                else:
                    xbmc.log(
                        '[CLEANUI] La reproduccion no comenzo dentro '
                        'del tiempo limite',
                        xbmc.LOGWARNING,
                    )
                return False

            xbmc.log(
                '[CLEANUI] fullscreenvideo visible y disponible para el mando',
                xbmc.LOGINFO,
            )

            self.end_transition()

            self._close_busy_dialogs(
                'fullscreenvideo visible',
                write_log=True,
            )

            hidden_since = None
            last_recovery = 0.0
            recovery_attempts = 0
            stopped_ticks = 0
            closing_transition_started = False
            next_busy_check = time.monotonic() + 5.0
            prev_state = None

            while not monitor.abortRequested():
                try:
                    playing_video = player.isPlayingVideo()
                    playing = playing_video or player.isPlaying()
                except Exception:
                    playing_video = False
                    playing = False

                has_video = xbmc.getCondVisibility('Player.HasVideo')
                has_audio = xbmc.getCondVisibility('Player.HasAudio')
                has_media = (
                    xbmc.getCondVisibility('Player.HasMedia')
                    or has_video
                    or has_audio
                )
                fullscreen_visible = xbmc.getCondVisibility(
                    'Window.IsVisible(fullscreenvideo)'
                )

                current_state = (
                    playing,
                    playing_video,
                    has_media,
                    has_video,
                    has_audio,
                    fullscreen_visible,
                )

                if current_state != prev_state:
                    xbmc.log(
                        '[CLEANUI] Estado de reproduccion: '
                        'playing={} playing_video={} has_media={} '
                        'has_video={} has_audio={} fullscreen={}'.format(
                            playing,
                            playing_video,
                            has_media,
                            has_video,
                            has_audio,
                            fullscreen_visible,
                        ),
                        xbmc.LOGINFO,
                    )
                    prev_state = current_state

                # Después de detener el vídeo, Android TV puede conservar
                # Player.HasMedia=True durante bastante tiempo. Lo importante es que
                # ya no esté reproduciendo y fullscreenvideo haya desaparecido.
                if not playing and not fullscreen_visible:
                    if not closing_transition_started:
                        # Cubrir Videos desde la primera señal de cierre. Las
                        # muestras siguientes confirman que no fue transitoria.
                        self.begin_transition()
                        closing_transition_started = True
                    stopped_ticks += 1
                else:
                    if closing_transition_started:
                        # Falso positivo transitorio: el reproductor volvió.
                        self.end_transition()
                        closing_transition_started = False
                    stopped_ticks = 0

                if playing and not fullscreen_visible:
                    now = time.monotonic()
                    if hidden_since is None:
                        hidden_since = now
                    hidden_for = now - hidden_since
                    if (
                        recovery_attempts < 2
                        and hidden_for >= (1.0 if recovery_attempts == 0 else 4.0)
                        and now - last_recovery >= 2.0
                    ):
                        recovery_attempts += 1
                        last_recovery = now
                        xbmc.log(
                            '[CLEANUI] Video oculto; recuperando '
                            'fullscreenvideo ({}/2)'.format(recovery_attempts),
                            xbmc.LOGINFO,
                        )
                        xbmc.executebuiltin(
                            'ActivateWindow(fullscreenvideo)'
                        )
                    if hidden_for >= 8.0:
                        xbmc.log(
                            '[CLEANUI] No se pudo recuperar fullscreenvideo; '
                            'deteniendo antes de restaurar Clean UI',
                            xbmc.LOGWARNING,
                        )
                        self._stop_player_safely(
                            player,
                            'video oculto detras de la interfaz',
                        )
                        break
                else:
                    hidden_since = None
                    recovery_attempts = 0

                if stopped_ticks >= 2:
                    xbmc.log(
                        '[CLEANUI] Reproductor cerrado; iniciando restauracion',
                        xbmc.LOGINFO,
                    )
                    break

                now = time.monotonic()
                if now >= next_busy_check:
                    next_busy_check = now + 5.0
                    if (
                        fullscreen_visible
                        and (playing or has_media)
                        and self._busy_dialog_visible()
                    ):
                        self._close_busy_dialogs(
                            'vigilancia durante reproduccion',
                            write_log=False,
                        )

                xbmc.sleep(100)

            return playback_started

        except Exception:
            if (
                self._player_is_playing(player)
                or self._player_has_media()
            ):
                self._stop_player_safely(
                    player,
                    'excepcion dentro de _run_player',
                )
            raise

        finally:
            self._close_busy_dialogs(
                'salida del reproductor',
                write_log=False,
            )

    def _wait_before_restore(self):
        """
        Espera brevemente a que fullscreenvideo desaparezca.
        No bloquea la restauración durante 10-20 segundos por propiedades
        Player.HasMedia obsoletas, algo frecuente en Android TV.
        """
        player = xbmc.Player()
        monitor = xbmc.Monitor()
        xbmc.log(
            '[CLEANUI] Comprobando cierre del reproductor antes de restaurar',
            xbmc.LOGINFO,
        )

        clean_ticks = 0
        stopped_ticks = 0
        # Máximo aproximado: 1 segundo.
        for unused in range(10):
            if monitor.abortRequested():
                return False

            playing = self._player_is_playing(player)
            fullscreen_visible = xbmc.getCondVisibility(
                'Window.IsVisible(fullscreenvideo)'
            )

            # El reproductor ya no reproduce y fullscreenvideo desapareció.
            if not playing and not fullscreen_visible:
                stopped_ticks += 1
            else:
                stopped_ticks = 0

            # Player.HasMedia puede quedar obsoleto en Android TV. Dos muestras
            # sin reproducción y sin fullscreenvideo bastan para restaurar.
            if not playing and not fullscreen_visible:
                clean_ticks += 1
            else:
                clean_ticks = 0

            if clean_ticks >= 2:
                break

            xbmc.sleep(100)

        self._close_busy_dialogs(
            'antes de restaurar navegacion',
            write_log=False,
        )

        if monitor.abortRequested():
            return False

        # Al vencer el timeout, no restaurar encima de un reproductor aún activo.
        if playing or fullscreen_visible:
            xbmc.log(
                '[CLEANUI] Timeout de restauracion: el reproductor sigue '
                'activo (playing={}, fullscreen={}); no se restaura'.format(
                    playing, fullscreen_visible
                ),
                xbmc.LOGWARNING,
            )
            return False

        xbmc.log(
            '[CLEANUI] Cierre comprobado; restaurando interfaz inmediatamente',
            xbmc.LOGINFO,
        )
        return True

    def _drain_pending_playback(self):
        if self._processing_playback:
            return

        self._processing_playback = True
        try:
            while self._pending_playback and not self.exit_requested:
                request = self._pending_playback
                self._pending_playback = None
                self._restored_stack = None
                path = request.get('path')
                screens = list(request.get('screens') or [])

                screen_names = [
                    getattr(screen, 'screen_type', 'unknown')
                    for screen in screens
                ]

                xbmc.log(
                    '[CLEANUI] Pila guardada para reproduccion: {}'.format(
                        ' -> '.join(screen_names) if screen_names else '(vacia)'
                    ),
                    xbmc.LOGINFO,
                )

                try:
                    self._run_player(path)
                except Exception:
                    xbmc.log(
                        '[CLEANUI] Error durante la reproduccion:\n{}'.format(
                            traceback.format_exc()
                        ),
                        xbmc.LOGERROR,
                    )
                finally:
                    # Ocultar el intervalo entre fullscreenvideo y la ventana
                    # restaurada.
                    if not self.exit_requested:
                        self.begin_transition()

                if self.exit_requested:
                    xbmc.log(
                        '[CLEANUI] No se restaurará la interfaz porque se '
                        'solicitó salir',
                        xbmc.LOGINFO,
                    )
                    break

                if xbmc.Monitor().abortRequested():
                    break

                if not self._wait_before_restore():
                    # No dejar la cortina abierta si se aborta la restauración.
                    self.end_transition()
                    break

                # NO bloquear la restauración esperando una petición a Disney+.
                # El refresco de Continue Watching no puede bloquear la vuelta
                # a la interfaz.
                # self._refresh_after_playback(screens)

                xbmc.log(
                    '[CLEANUI] Restaurando navegacion de {} pantallas: {}'.format(
                        len(screens),
                        ' -> '.join(screen_names)
                        if screen_names else '(vacia)',
                    ),
                    xbmc.LOGINFO,
                )

                for index in range(len(screens) - 1, -1, -1):
                    if self.exit_requested:
                        xbmc.log(
                            '[CLEANUI] Restauración cancelada por salida explícita',
                            xbmc.LOGINFO,
                        )
                        break
                    if self._pending_playback:
                        break
                    if xbmc.Monitor().abortRequested():
                        break

                    screen = screens[index]
                    screen_type = getattr(
                        screen,
                        'screen_type',
                        'unknown',
                    )

                    self._restored_stack = screens[:index + 1]

                    xbmc.log(
                        '[CLEANUI] Restaurando pantalla {} de {}: {}'.format(
                            index + 1,
                            len(screens),
                            screen_type,
                        ),
                        xbmc.LOGINFO,
                    )

                    try:
                        self._restore_screen(screen)
                    except Exception:
                        xbmc.log(
                            '[CLEANUI] Error restaurando pantalla {} '
                            '({}):\n{}'.format(
                                index,
                                screen_type,
                                traceback.format_exc(),
                            ),
                            xbmc.LOGERROR,
                        )
                    finally:
                        self._restored_stack = None

                    if self.exit_requested:
                        xbmc.log(
                            '[CLEANUI] El usuario salió durante la restauración',
                            xbmc.LOGINFO,
                        )
                        break

                    if xbmc.Monitor().abortRequested():
                        break
        finally:
            self._restored_stack = None
            self._processing_playback = False

    def _refresh_after_playback(self, screens):
        """Refresh Continue Watching without rebuilding Home."""
        home_screen = None
        for screen in screens:
            if getattr(screen, 'screen_type', '') == 'home':
                home_screen = screen
                break

        if not home_screen:
            xbmc.log(
                '[CLEANUI] Refresco posterior a reproduccion: '
                'no hay pantalla Home en la pila',
                xbmc.LOGINFO,
            )
            return False

        try:
            refreshed = self.repository.refresh_continue_watching(
                home_screen
            )
        except Exception:
            xbmc.log(
                '[CLEANUI] Error refrescando Continue Watching:\n'
                '{}'.format(traceback.format_exc()),
                xbmc.LOGWARNING,
            )
            return False

        xbmc.log(
            '[CLEANUI] Refresco posterior a reproduccion: {}'.format(
                'actualizado' if refreshed else 'sin cambios'
            ),
            xbmc.LOGINFO,
        )
        return refreshed

    def _open_detail(self, builder, context, *args):
        try:
            with gui.busy():
                screen = builder(*args)

            if not screen:
                raise RuntimeError(
                    'La API no devolvió contenido para la pantalla'
                )

            if (
                not screen.hero
                and getattr(screen, 'screen_type', '') != 'search'
            ):
                raise RuntimeError(
                    'La API no devolvió contenido para la pantalla'
                )

            window = DetailWindow(
                'ui_detail.xml',
                self.addon_path,
                'Default',
                '1080i',
                controller=self,
                screen=screen,
            )

            self._show_window(window)
            del window
            return True

        except Exception:
            self._show_error(context)
            return False

    def open_home(self):
        try:
            timer = PerfTimer('open_home')
            with gui.busy():
                screen = self.repository.build_home()
            timer.mark('build_home')

            window = HomeWindow(
                'uihome.xml',
                self.addon_path,
                'Default',
                '1080i',
                controller=self,
                screen=screen,
                screen_kind='home',
            )

            self._show_window(window)
            timer.mark('window_closed')
            del window
            return True

        except Exception:
            self._show_error('open_home')
            return False

    def open_movie(self, deeplinkid):
        return self._open_detail(
            self.repository.build_movie_detail,
            'open_movie',
            deeplinkid,
        )

    def open_show(self, showid):
        return self._open_detail(
            self.repository.build_show_detail,
            'open_show',
            showid,
        )

    def open_season(self, showid, seasonid):
        return self._open_detail(
            self.repository.build_season_detail,
            'open_season',
            showid,
            seasonid,
        )

    def open_search(self):
        query = xbmcgui.Dialog().input(
            'Buscar',
            type=xbmcgui.INPUT_ALPHANUM,
        ).strip()

        if not query:
            return False

        return self._open_detail(
            self.repository.build_search,
            'open_search',
            query,
        )

    def _open_home_like(
        self,
        builder,
        context,
        screen_kind='home',
        source_window=None,
    ):
        try:
            with gui.busy():
                screen = builder()

            if not screen:
                raise RuntimeError(
                    'La API no devolvió contenido para la pantalla'
                )

            screen.screen_kind = screen_kind

            # Reutilizar la ventana Home ya abierta en lugar de apilar un nuevo
            # WindowXMLDialog: evita el crecimiento de ventanas (lag/doble
            # interfaz en Chromecast). Se guarda el Screen actual en la pila
            # para que BACK recargue la seccion anterior.
            if source_window and source_window in self._windows:
                if getattr(source_window, 'screen', None):
                    self._home_stack.append((
                        source_window.screen,
                        source_window.screen_kind,
                    ))
                return source_window.replace_screen(
                    screen,
                    screen_kind,
                )

            window = HomeWindow(
                'uihome.xml',
                self.addon_path,
                'Default',
                '1080i',
                controller=self,
                screen=screen,
                screen_kind=screen_kind,
            )

            self._show_window(window)
            del window
            return True

        except Exception:
            self._show_error(context)
            return False

    def open_movies(self, source_window=None):
        xbmc.log(
            '[CLEANUI] Abriendo Home de peliculas',
            xbmc.LOGINFO,
        )
        return self._open_home_like(
            self.repository.build_movies_home,
            'open_movies',
            screen_kind='movies',
            source_window=source_window,
        )

    def open_series(self, source_window=None):
        xbmc.log(
            '[CLEANUI] Abriendo Home de series',
            xbmc.LOGINFO,
        )
        return self._open_home_like(
            self.repository.build_series_home,
            'open_series',
            screen_kind='series',
            source_window=source_window,
        )

    def open_watchlist(self, source_window=None):
        xbmc.log(
            '[CLEANUI] Abriendo Mi lista dentro de Clean UI',
            xbmc.LOGINFO,
        )
        return self._open_home_like(
            self.repository.build_watchlist_screen,
            'open_watchlist',
            screen_kind='watchlist',
            source_window=source_window,
        )

    def open_continue_watching(self, source_window=None):
        xbmc.log(
            '[CLEANUI] Abriendo Continuar viendo dentro de Clean UI',
            xbmc.LOGINFO,
        )
        return self._open_home_like(
            self.repository.build_continue_watching_screen,
            'open_continue_watching',
            screen_kind='continue_watching',
            source_window=source_window,
        )

    def select_profile(self, source_window=None):
        """Open SlyGuy's profile selector and rebuild the current Home."""
        if self._selecting_profile:
            xbmc.log(
                '[CLEANUI] Selector de perfil ignorado porque ya está abierto',
                xbmc.LOGINFO,
            )
            return False
        self._selecting_profile = True
        try:
            from slyguy import userdata
            import resources.lib.plugin as core
            previous_profile_id = userdata.get('profile_id') or ''
            xbmc.log(
                '[CLEANUI] Abriendo selector de perfil; perfil actual={}'.format(
                    previous_profile_id
                ),
                xbmc.LOGINFO,
            )
            changed = core._select_profile()
            current_profile_id = userdata.get('profile_id') or ''
            if changed is False:
                xbmc.log(
                    '[CLEANUI] Selección de perfil cancelada',
                    xbmc.LOGINFO,
                )
                return False
            if current_profile_id == previous_profile_id:
                xbmc.log(
                    '[CLEANUI] El perfil seleccionado no cambió',
                    xbmc.LOGINFO,
                )
                return False
            xbmc.log(
                '[CLEANUI] Perfil cambiado: anterior={} nuevo={}'.format(
                    previous_profile_id,
                    current_profile_id,
                ),
                xbmc.LOGINFO,
            )
            # Las pantallas guardadas pertenecen al perfil anterior y no
            # deben poder restaurarse mediante BACK.
            self._home_stack = []
            # Un Repository nuevo evita conservar modelos o resultados
            # visuales del perfil anterior. Las cachés válidas de red
            # continúan gestionadas por API.
            self.repository = Repository()
            with gui.busy():
                screen = self.repository.build_home()
            if not screen:
                raise RuntimeError(
                    'No se pudo reconstruir Home para el nuevo perfil'
                )
            if not source_window:
                xbmc.log(
                    '[CLEANUI] No existe una ventana Home para aplicar el perfil',
                    xbmc.LOGWARNING,
                )
                return False
            return source_window.replace_screen(screen, 'home')
        except Exception:
            self._show_error('select_profile')
            return False
        finally:
            self._selecting_profile = False

    def open_collection(self, page_id, title, source_window=None):
        xbmc.log(
            '[CLEANUI] Abriendo industria: nombre={} page_id={}'.format(
                title, page_id,
            ),
            xbmc.LOGINFO,
        )
        try:
            with gui.busy():
                screen = self.repository.build_collection(page_id, title)

            if not screen:
                raise RuntimeError(
                    'La API no devolvió contenido para la pantalla'
                )

            screen.screen_kind = 'collection'

            if source_window and source_window in self._windows:
                if getattr(source_window, 'screen', None):
                    self._home_stack.append((
                        source_window.screen,
                        source_window.screen_kind,
                    ))
                return source_window.replace_screen(
                    screen,
                    'collection',
                )

            window = HomeWindow(
                'uihome.xml',
                self.addon_path,
                'Default',
                '1080i',
                controller=self,
                screen=screen,
                screen_kind='collection',
            )

            self._show_window(window)
            del window
            return True

        except Exception:
            self._show_error('open_collection')
            return False
