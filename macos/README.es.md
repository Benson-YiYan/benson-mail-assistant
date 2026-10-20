# Asistente de correo electrónico para Mac

[简体中文](README.md) · [English](README.en.md) · [Proyecto](../README.es.md)

Organiza cada correo nuevo en **aviso, remitente, resumen, acciones, contenido de los adjuntos y propuesta de respuesta**. Admite varios buzones, la IA que elijas, Markdown, búsqueda y filtros. Sin correo nuevo no se llama a la IA. Nunca se envían respuestas automáticamente.

## Instalación: Apple silicon e Intel

Se requiere **macOS 14 o posterior**, incluido Sonoma 14.8.9. En menú Apple → Acerca de este Mac comprueba el chip: descarga el DMG `Mac-AppleSilicon` para los chips de Apple o `Mac-Intel` para Intel desde [GitHub Releases](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest). Comprueba `SHA256SUMS.txt`.

Abre el DMG, arrastra la aplicación a Aplicaciones y ábrela allí. Incluye su entorno de ejecución; no necesitas Python ni Homebrew. El modo API no requiere Codex. Las versiones usan la hora real de compilación de Pekín, `yyyyMMddHHmm`.

La aplicación tiene firma ad-hoc, sin Developer ID ni certificación notarial de Apple. Si macOS bloquea la apertura, verifica el origen y SHA256, intenta abrir una vez y ve a Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente, si aparece. Confirma la siguiente solicitud. No desactives Gatekeeper globalmente; en equipos gestionados o sin esa opción consulta al administrador.

## Configuración inicial

1. Elige proveedor u Otro correo (IMAP personalizado). Activa IMAP en el proveedor e introduce dirección completa y contraseña de aplicación, código de autorización o token OAuth2 requerido. Para otro proveedor indica servidor, puerto y cifrado. Deja el usuario avanzado en blanco para usar tu dirección salvo que el proveedor indique lo contrario. Abre ¿Cómo obtengo un código de autorización?, guarda y prueba la conexión.
2. En Servicio de IA, elige API, Codex o DeepSeek Harness, guarda y prueba. API necesita URL base compatible con Chat Completions, clave y modelo. Codex debe estar instalado y con sesión iniciada; Harness debe estar instalado y configurado y admitir `headless --json`. No se incluye ni descarga Harness. Probar la IA envía un mensaje corto y puede consumir saldo.
3. En Configuración general usa Examinar para elegir la carpeta de informes e inicia la supervisión.

Hay preajustes para 163, 126, Yeah, QQ/Foxmail, Tencent Exmail, Gmail, Outlook/Microsoft 365, iCloud y Yahoo. Los preajustes no autorizan la cuenta. Los tokens OAuth2 se renuevan manualmente; la organización puede restringir IMAP. Consulta la [guía del correo](Resources/Mail-account-setup-es.txt).

## Idioma

El primer inicio elige chino para un sistema chino, español para uno español e inglés para los demás. Cambia el idioma en Configuración general. Si falta un paquete, aparece «No has descargado este idioma. ¿Quieres descargarlo ahora?». Puedes descargarlo o cancelar y conservar el actual. Los informes nuevos usan el idioma elegido, con los mismos seis requisitos; los anteriores no cambian. La propuesta de respuesta sigue el idioma del mensaje recibido.

## Navegación e informes

- **Informes de correo:** selecciona a la izquierda y lee a la derecha; copia el Markdown original, abre el archivo, busca y filtra por fechas, remitente y adjuntos.
- **Correo y comprobaciones:** gestiona cuentas, prueba conexiones, ajusta intervalo y controla la supervisión. Pausa y espera al fin de la tarea antes de cambiar conexiones.
- **Servicio de IA:** elige, configura y prueba la IA.
- **Configuración general:** idioma, carpeta, inicio de sesión, actualizaciones y desinstalación.
- **Ayuda:** guía de uso, autorización del correo, actualizaciones y Acerca de.

Intervalo predeterminado: 60 segundos; ajustable entre 10 y 86400. La primera comprobación de un buzón nuevo registra su punto de partida y no analiza todo el correo antiguo. Con progreso guardado, al reanudar se comprueban mensajes recibidos durante pausas o apagados si siguen en la carpeta seleccionada.

Los informes nuevos usan `carpeta/fecha/asunto-hora-de-recepción.md`, con fecha y hora de Pekín y nombres sin colisiones. La vista previa admite títulos, negrita, listas anidadas, enlaces, tablas y código; los TXT antiguos siguen disponibles. La búsqueda cubre los datos locales, no todo el servidor. Cambiar de carpeta solo afecta a informes nuevos.

## Proxy

Cada buzón admite Directa, Sistema, HTTP CONNECT o SOCKS5. Inicia v2rayN u otro proxy y en las opciones de conexión elige el protocolo, dirección y puerto reales. Activa el proxy del sistema si eliges Sistema. Guarda y prueba; los fallos no usan conexión directa silenciosamente. No se requiere TUN para proxy explícito. Solo afecta a IMAP; no a la API de IA. No se admiten PAC ni proxies con usuario y contraseña.

## Actualizaciones, salida y desinstalación

Se comprueban actualizaciones cada hora o desde Ayuda → Buscar actualizaciones. La descarga, progreso y verificación se realizan dentro de la aplicación. La instalación requiere tu acción, conserva configuración e informes e intenta restaurar la versión anterior si falla. El manifiesto estable está en [`distribution/manifest.json`](../distribution/manifest.json) del repositorio común.

Cerrar la ventana mantiene la supervisión en la barra de menús. Salir desde el Dock, el menú o ⌘Q detiene la supervisión y guarda una pausa. Vuelve a abrir e inicia la supervisión para continuar.

Desinstala desde Configuración general. Puedes conservar configuración e informes por separado. Eliminar informes requiere confirmación adicional. Conservar configuración conserva las credenciales de esta aplicación en el Llavero para reinstalar; se borran caché y progreso.

## Errores y datos

Prueba la conexión y consulta fase, tipo de excepción y respuesta del servidor sin credenciales. Para autenticación revisa cuenta y credenciales; para IMAP desactivado, correo web o administrador; para Unsafe Login, los avisos de seguridad; para DNS, tiempo de espera o TLS, servidor, puerto, red, hora y proxy.

Las credenciales y claves API están en el Llavero. Los mensajes y texto legible de adjuntos se envían a la IA elegida. El buzón se consulta en modo de solo lectura. Imágenes, escaneos, documentos cifrados o no compatibles tienen límites; revisa el original antes de responder.

## Desarrollo

Código en `Sources` y `Runtime`. Consulta [Compilación y pruebas](docs/DEVELOPMENT.md). Los usuarios pueden usar el DMG. Intel se prueba mediante Rosetta en Apple silicon, no en hardware Intel físico.

## Volver a resumir y preguntar sobre un correo

Selecciona un informe y elige Volver a resumir para generar las seis secciones en el idioma actual de la interfaz. Si falla, se conserva el informe anterior. Se utiliza el índice guardado del correo; los informes antiguos sin ese índice muestran una explicación.

Preguntar sobre este correo permite preguntas de seguimiento y archivos adicionales mediante el selector. Cada correo conserva su propia conversación para continuar después. El contexto incluye el correo original, los adjuntos legibles, el informe actual y la conversación. Si crece demasiado, se resumen los turnos antiguos, se mantienen los recientes y se indica la compresión. El resumen no conserva cada palabra; el historial completo permanece guardado localmente. Cita y verifica cifras o frases importantes.

Estas acciones utilizan la IA configurada y pueden generar costes. Los archivos adicionales se leen solo para extraer texto; los archivos ilegibles o demasiado grandes producen un error explícito. No se envían correos. El historial se guarda en los datos locales de la aplicación. Se elimina al desinstalar, aunque conserves la configuración del correo y de IA; copia antes las conversaciones que necesites.

## Reglas de remitentes y correo no deseado

En Buzones y comprobación → Bloquear correos, elige una lista negra o una lista blanca. Se omiten los remitentes de la lista negra; la lista blanca solo permite resumir los remitentes incluidos. Una lista blanca vacía omite todos los correos nuevos. Las reglas se aplican a todos los buzones y comparan direcciones completas sin distinguir mayúsculas. Puedes añadir, seleccionar en lote o quitar direcciones.

«No resumir correo no deseado (algunos proveedores pueden no admitirlo)» utiliza marcas explícitas del servidor, cabeceras o carpetas de correo no deseado. No adivina por el asunto ni llama a la IA para clasificarlo. Solo se comprueba la carpeta configurada; sin indicadores del proveedor no se puede identificar. La opción está desactivada por defecto.

Los mensajes omitidos se agrupan por remitente en los registros locales. Puedes resumir uno o varios con el idioma y la IA actuales. Es una excepción para esa ocasión y no cambia las reglas; los fallos conservan el registro. Eliminar registro solo borra el registro local, nunca el correo original. Las reglas afectan a los mensajes nuevos comprobados y no eliminan informes existentes.

Arrastra el divisor entre el informe y la conversación del correo para ajustar el tamaño de ambas áreas.
