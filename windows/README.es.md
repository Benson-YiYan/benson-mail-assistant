# Asistente de correo electrónico para Windows

[简体中文](README.md) · [English](README.en.md) · [Proyecto](../README.es.md)

Cada correo nuevo se convierte en **aviso, remitente, resumen, acciones, contenido de los adjuntos y propuesta de respuesta**. Varios buzones, tu IA, Markdown, búsqueda y filtros. Sin correo nuevo no se llama a la IA. Nunca se envían respuestas automáticamente.

## Instalar

Requiere **Windows 10 / 11 x64**. Descarga `BensonMail-Windows-x64-Setup-<versión>.exe` de [GitHub Releases](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest). Comprueba `SHA256SUMS.txt`, ejecútalo y elige ubicación y accesos directos de aplicación y desinstalador en escritorio y menú Inicio. Puede actualizar una instalación existente. Al terminar puedes elegir eliminar el instalador cuando se cierre.

El instalador detecta **.NET 8 x64 y Windows App Runtime 1.8 x64 (WinUI 3)**. Reutiliza los compatibles y pide confirmación antes de descargar e instalar los que falten; puede requerir permiso administrativo. Rechazar o fallar la instalación de componentes deja la aplicación anterior sin modificar. Una actualización correcta elimina las copias antiguas de entornos incluidos solo si coinciden rutas registradas y SHA256. Desinstalar no elimina los componentes compartidos del sistema. No necesitas Python ni terminal. API no requiere Codex.

No hay firma de editor del instalador; verifica su origen si Windows avisa. Las versiones corresponden a la hora real de compilación de Pekín, `yyyyMMddHHmm`.

## Idiomas

Aplicación, instalador y desinstalador admiten chino simplificado, inglés y español. El instalador detecta chino/español del sistema y usa inglés en los demás casos. Puedes seleccionar Descargar chino simplificado, Descargar inglés y Descargar español.

En Configuración general puedes cambiar el idioma. Si no está descargado, aparece «No has descargado este idioma. ¿Quieres descargarlo ahora?». Confirma o conserva el actual. Los informes nuevos mantienen las seis secciones y usan el idioma elegido; los anteriores no cambian. Los borradores siguen el idioma del mensaje entrante.

## Configuración inicial

1. Elige proveedor u Otro correo (IMAP personalizado), activa IMAP con tu proveedor e introduce dirección completa y contraseña de aplicación, código de autorización o token OAuth2 requerido. Otro correo necesita servidor, puerto y cifrado. Deja el usuario avanzado vacío salvo que tu proveedor lo requiera. Usa ¿Cómo obtengo un código de autorización?, guarda y prueba.
2. Elige y prueba la IA: API compatible con Chat Completions (URL base, clave y modelo), Codex instalado y con sesión iniciada, o DeepSeek Harness instalado y configurado con soporte `headless --json`. Harness no se incluye ni se descarga. El modo API acepta URL base `/v1` o URL completa `/chat/completions`. Probar la IA puede consumir saldo.
3. Usa Examinar para elegir la carpeta de informes e inicia la supervisión.

Preajustes: 163, 126, Yeah, QQ/Foxmail, Tencent Exmail, Gmail, Outlook/Microsoft 365, iCloud y Yahoo. Se requiere autorización de cuenta. OAuth2 se introduce y renueva manualmente; la herramienta Microsoft requiere ID de cliente propio, aprobación en navegador y, a veces, administrador. No renueva tokens. Consulta la [guía completa del correo](docs/Mail-account-setup-es.txt).

## Supervisión e informes

- Predeterminado: 60 segundos; configurable entre 10 y 86400.
- La primera comprobación registra el punto de partida del buzón; no analiza todos los mensajes antiguos.
- Con progreso guardado, al reanudar se comprueban los recibidos durante pausas o apagados que permanezcan en la carpeta. Pausa y espera al fin de tareas antes de editar conexiones.
- Nuevos informes: `carpeta/fecha/asunto-hora-de-recepción.md`, con hora de Pekín y nombres sin colisiones. La vista previa admite títulos, negrita, listas, enlaces, tablas y código. Los TXT antiguos siguen disponibles.
- Busca en cuerpo, remitente, nombres de adjuntos e informes locales. Combina filtros de fechas, remitente y adjuntos; no se busca en todo el buzón remoto.
- Abrir informe abre el archivo; Abrir carpeta de informes abre su carpeta.

## Proxy

En Opciones avanzadas de conexión y proxy de cada cuenta elige Directa, Sistema, HTTP CONNECT o SOCKS5. Inicia v2rayN u otro cliente y usa dirección, puerto y protocolo reales. 10808 es solo un ejemplo. Guarda y prueba antes de reanudar. Un fallo no cambia silenciosamente a conexión directa. No necesitas TUN para un proxy explícito. Solo afecta a IMAP, no a la API de IA. No se admiten PAC ni proxies con usuario y contraseña.

## Actualizaciones y desinstalación

Se buscan actualizaciones cada cinco horas o manualmente. Descarga, cancelación, reintento y verificación ocurren dentro de la aplicación; instalar requiere tu acción. Se conservan configuración, informes y opciones de accesos directos. El manifiesto estable está en [`distribution/manifest.json`](../distribution/manifest.json) del repositorio común.

Cerrar la ventana mantiene la supervisión en la bandeja. Pulsa el sobre para restaurar. Salir detiene la sesión actual; el inicio con Windows es opcional.

Desinstala desde su acceso directo o Aplicaciones instaladas de Windows. Si está en ejecución, se pide permiso para cerrarla; espera al fin de procesamiento activo. Los interruptores de conservar configuración e informes tienen etiquetas fijas. Desactivar conservar informes pide otra confirmación antes de borrar. Las credenciales conservadas solo funcionan para el mismo usuario de Windows en el mismo equipo.

## Conexión y datos

Prueba la conexión y consulta fase, tipo de excepción y respuesta del servidor. Para autenticación revisa cuenta y credenciales; para IMAP desactivado, correo web/administrador; para Unsafe Login, avisos de seguridad; para DNS, tiempo de espera o TLS, servidor, puerto, red, hora y proxy. El antiguo mensaje genérico «La operación falló. Revisa configuración y permisos» no demuestra un problema de permisos: actualiza para obtener detalles.

Claves y credenciales se cifran para el usuario actual de Windows. Texto de mensajes y adjuntos legibles se envían a la IA elegida. IMAP es de solo lectura y no se envían respuestas automáticamente. Escaneos, imágenes, documentos cifrados y formatos no admitidos tienen límites; revisa el original.

## Desarrollo

Código en `windows/` de este repositorio. Consulta [Desarrollo](docs/DEVELOPMENT.md) y [el proyecto](../README.es.md).

## Volver a resumir y preguntar sobre un correo

Selecciona un informe y elige Volver a resumir para generar las seis secciones en el idioma actual de la interfaz. Si falla, se conserva el informe anterior. Se utiliza el índice guardado del correo; los informes antiguos sin ese índice muestran una explicación.

Preguntar sobre este correo permite preguntas de seguimiento y archivos adicionales mediante el selector. Cada correo conserva su propia conversación para continuar después. El contexto incluye el correo original, los adjuntos legibles, el informe actual y la conversación. Si crece demasiado, se resumen los turnos antiguos, se mantienen los recientes y se indica la compresión. El resumen no conserva cada palabra; el historial completo permanece guardado localmente. Cita y verifica cifras o frases importantes.

Estas acciones utilizan la IA configurada y pueden generar costes. Los archivos adicionales se leen solo para extraer texto; los archivos ilegibles o demasiado grandes producen un error explícito. No se envían correos. El historial se guarda en los datos locales de la aplicación. Se elimina al desinstalar, aunque conserves la configuración del correo y de IA; copia antes las conversaciones que necesites.

## Reglas de remitentes y correo no deseado

En Buzones y comprobación → Bloquear correos, elige una lista negra o una lista blanca. Se omiten los remitentes de la lista negra; la lista blanca solo permite resumir los remitentes incluidos. Una lista blanca vacía omite todos los correos nuevos. Las reglas se aplican a todos los buzones y comparan direcciones completas sin distinguir mayúsculas. Puedes añadir, seleccionar en lote o quitar direcciones.

«No resumir correo no deseado (algunos proveedores pueden no admitirlo)» utiliza marcas explícitas del servidor, cabeceras o carpetas de correo no deseado. No adivina por el asunto ni llama a la IA para clasificarlo. Solo se comprueba la carpeta configurada; sin indicadores del proveedor no se puede identificar. La opción está desactivada por defecto.

Los mensajes omitidos se agrupan por remitente en los registros locales. Puedes resumir uno o varios con el idioma y la IA actuales. Es una excepción para esa ocasión y no cambia las reglas; los fallos conservan el registro. Eliminar registro solo borra el registro local, nunca el correo original. Las reglas afectan a los mensajes nuevos comprobados y no eliminan informes existentes.
