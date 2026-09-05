# Max Clean UI — revisión 0.2.0

## Primera adaptación HBO Max para TV

Esta actualización modifica el mismo add-on, no crea una aplicación externa.
La referencia visual fue la web de HBO Max: perfiles, Inicio, Series y fichas.
Se adaptan a mando el menú superior, la paleta negra/blanca, las tarjetas,
los perfiles circulares, las fichas y el selector de temporadas con episodios.
HBO y Niños y Familia se muestran únicamente si el servicio ofrece su destino.

La interfaz se aloja en una extensión de biblioteca dentro del mismo add-on.
Así termina la petición de carpeta antes de mantener abierta la ventana visual.
La biblioteca se invoca por ID para preservar identidad y dependencias en Kodi.
Cancelar el diálogo de reproducción ya no añade una espera de 60 segundos.
Las transiciones no abren una cortina modal negra que dependa de recibir foco.
La propiedad de sesión se libera al cancelar perfiles, salir o fallar la carga.

Los archivos originales api.py, plugin.py, constants.py y settings.py no cambian
respecto a 0.1.6. El cambio de perfil delega el PIN y la autenticación al núcleo
original. No se modifican DRM, manifiestos de reproducción ni configuración de audio.

## Verificación y límites de esta entrega

Pruebas automatizadas locales: 96 casos con dobles de Kodi, más la prueba de
distribución. Se comprueban XML, sintaxis Python, paquete y paridad del núcleo.
No se ha ejecutado ni renderizado esta versión en Kodi o en un Chromecast real.
No se presentan mediciones de rendimiento en el dispositivo que no se han hecho.

No es todavía una réplica completa de la aplicación oficial: búsqueda utiliza el
teclado de Kodi, Mi lista conserva carriles y no la cuadrícula con pestañas de la
web, y faltan las pestañas de géneros y otros detalles de composición. No se han
añadido creación/edición de perfiles, gestión de suscripciones ni calificaciones
sin soporte del add-on. No hay previsualización automática de vídeo.

Prueba de aceptación en TV: cancelar Continuar viendo, entrar en serie y cambiar
temporada, volver una vez con Atrás, reproducir/detener y cerrar/reabrir el add-on.
Conservar la versión anterior permite volver atrás si aparece una regresión.

## Historial: revisión 0.1.6

## Corrección tras la prueba en Chromecast

- Se elimina el avance adicional del encabezado: Kodi ya procesa el movimiento
  nativo antes de notificar onAction. Se lee una sola vez la selección real.
- Carátulas: se usan URLs de los objetos originales de imagen. Se conservan
  consultas de CDN, recorte, firmas y codificación. Se retira el redimensionado
  general introducido en 0.1.5; URLs simples conservan el ancho 600 de Slyguy.
- Temporadas con número válido no se descartan si falta el contador opcional
  de episodios. Se excluyen únicamente contadores explícitos de cero.
- Detalles: el foco inicial se decide por controles poblados y acciones
  disponibles; no depende de isVisible durante la inicialización del diálogo.
  Se actualiza la visibilidad nativa antes de solicitar el foco, sin esperas.
- Una pulsación de selección se activa únicamente mediante onClick; el callback
  onAction que Kodi envía después no vuelve a abrir la pantalla ni retrocede dos veces.
- Atrás desde páginas adicionales de Inicio respeta el historial antes de salir.
- Episodios con título de serie pero sin el campo name se conservan; imágenes
  opcionales ausentes no impiden construir su tarjeta.
- Tarjetas de películas/series más próximas y sin rótulo duplicado. Los rótulos
  de temporadas y controles de paginación se mantienen para identificarlos.
- Pantallas vacías no reservan el espacio de filas que no contienen elementos.
- Cachés de modelos no duplican los datos de origen de cada tarjeta. Se limitan
  a dos consultas adicionales de colecciones por bloque y se evita volver a
  pedir una Mi lista ya incluida en la respuesta inicial.

La verificación local reproduce el orden de eventos de Kodi, respuestas con
datos opcionales ausentes y URLs con parámetros. No sustituye una prueba de
renderizado y reproducción en el Chromecast real.

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
- Imágenes visuales: parámetros originales del CDN conservados en 0.1.6.
  Texturas en segundo plano, plantillas diferenciadas para pósteres y panorámicas,
  sin duplicar imágenes para el marco de foco; se evita autoscroll permanente.

## Base protegida

Se compara automáticamente la API completa, constantes y configuración con la
versión inicial. En plugin.py solo cambian index y las rutas clean_ui_*.
Autenticación, selector original de perfiles, obtención de streams, parser,
Widevine, procesamiento MPD y selección de audio permanecen idénticos.
No se cambian ajustes del sistema de audio de Kodi.
En el salto de 0.1.5 a 0.1.6, plugin.py, api.py, constants.py y settings.py se
conservan completos. La corrección de Disney 0.1.34 cambia únicamente la ventana
de Inicio y su manifest respecto a la fuente 0.1.33.

## Validación y límites

Resultado de esta revisión: 77 pruebas automatizadas de catálogo, ventanas y
layouts, más una de distribución, aprobadas. Disney incluye 17 regresiones de
selección/activación dentro de esa suite; requiere el checkout hermano para ejecutarlas.

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
