# Max Clean UI — revisión 0.1.5

Se revisaron los módulos Python, layouts XML, recursos y la distribución de Kodi.
La referencia es el código publicado de Max 0.1.4. Esta revisión no certifica el
funcionamiento del servicio ni sustituye una prueba en el Chromecast.

## Correcciones

- Cambio de perfil: se usa el objeto de perfil de Max, se respeta el bloqueo
  infantil y se descartan cachés/modelos de la sesión anterior.
- Entrada visual: un único controlador por sesión; el resultado de la ruta es
  una carpeta Kodi válida en lugar de un booleano. Una entrada duplicada durante
  la reproducción no abre otra interfaz.
- Transiciones: el detalle restaurado puede retirar la cortina al recuperar
  foco aunque tenga pantallas anteriores en el historial.
- Navegación: se guarda/restaura la selección al cambiar de sección; historial
  de seis pantallas y ocho filas visuales por página. Inicio reinicia el historial.
- Catálogo: los datos se normalizan en una copia antes del parser original.
  Una tarjeta incompleta no elimina todas las demás. Episodios sin edit conservan
  el enlace a su serie que entrega Slyguy.
- Colecciones, búsquedas, temporadas y Mi lista tienen paginación. Las categorías
  se recorren por bloques y las vistas previas permiten abrir la colección completa.
- Películas/Series usan su ruta dedicada si figura en el menú del servicio;
  en caso contrario filtran la ruta inicial, con más categorías accesibles.
- Caché visual por instancia/perfil, limitada a doce entradas; las ventanas
  reciben modelos independientes. Los metadatos de películas tienen un límite.
- La opción vacía de Continuar viendo se sustituye por Inicio. La integración
  actual no implementa sincronización de historial; no se afirma que el servicio
  carezca de esa capacidad. Se completa el contrato de refresco que estaba sin
  implementar (su llamada de reproducción ya estaba comentada).
- Imágenes visuales: tamaños solicitados de 360 px para póster y 1280 px para
  fondos; URLs con firmas reconocibles se conservan. La efectividad del CDN debe
  comprobarse en dispositivo. Carga de texturas en segundo plano y eliminación
  de layouts de estilos no utilizados en Home; se evita autoscroll permanente.

## Base protegida

Se compara automáticamente la API completa, constantes y configuración con la
versión inicial. En plugin.py solo cambian index y las rutas clean_ui_*.
Autenticación, selector original de perfiles, obtención de streams, parser,
Widevine, procesamiento MPD y selección de audio permanecen idénticos.
No se cambian ajustes del sistema de audio de Kodi.

## Validación y límites

Pruebas locales: parser original con fixtures sintéticos de catálogo, aislamiento
de caché/perfiles, paginación, rutas de películas, navegación, cortina, compilación
Python, IDs y destinos XML. Estas pruebas no ejecutan un Kodi real ni una cuenta
de Max. No se midieron FPS, RAM, red ni transcodificación AC3 en el Chromecast.

Prueba de aceptación en TV: actualizar y reiniciar Kodi; abrir Max; cambiar entre
dos perfiles; recorrer Inicio/Películas/Series; abrir una película, serie y
temporada; buscar y paginar; comprobar Mi lista; reproducir, pausar, detener y
volver al mismo punto. Confirmar español latino y salida AC3 con la configuración
existente. Registrar cualquier fallo con su pantalla, pasos y kodi.log redactado.

Pendientes de validar en dispositivo: comportamiento del foco con el mando,
respuestas reales y variantes del catálogo, paginación remota, imágenes del CDN,
sesiones largas, diferencias de skins/fuentes, compatibilidad con la versión
instalada de Kodi/Slyguy, calidad y audio. El keymap global preexistente y el
sondeo del reproductor conservan su comportamiento; requieren pruebas reales
antes de rediseñar esos mecanismos compartidos.
