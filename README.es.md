# Asistente de correo electrónico

[简体中文](README.md) · [English](README.en.md) · [Descargar](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest)

Convierte cada correo nuevo en seis secciones: **aviso, remitente, resumen, acciones pendientes, contenido de los adjuntos y propuesta de respuesta**.

Interfaces nativas para Windows y macOS, varios buzones y la IA que elijas. **Sin correo nuevo ni tareas pendientes de reintento, no se llama a la IA. Nunca se envían respuestas automáticamente.**

## Descargar e instalar

Descarga un instalador de la [última versión](https://github.com/Benson-YiYan/benson-mail-assistant/releases/latest). No necesitas código fuente ni terminal.

| Equipo | Paquete | Requisitos |
| --- | --- | --- |
| Windows x64 | `BensonMail-Windows-x64-Setup-….exe` | Windows 10 / 11 |
| Mac con chip de Apple | `BensonMail-Mac-AppleSilicon-….dmg` | macOS 14 o posterior |
| Mac con Intel | `BensonMail-Mac-Intel-….dmg` | macOS 14 o posterior |

Los paquetes de una misma publicación pueden tener números de versión distintos. Los números corresponden a la hora real de compilación en Pekín, `yyyyMMddHHmm`. Verifica las descargas mediante `SHA256SUMS.txt`.

- **Windows:** ejecuta el instalador, elige ubicación y accesos directos. Puede actualizar instalaciones existentes. Detecta .NET 8 y Windows App Runtime 1.8 (WinUI 3), reutiliza los compatibles y solicita confirmación antes de descargar componentes que falten. Su instalación puede pedir permisos de administrador. No se necesita Python; el modo API tampoco necesita Codex.
- **macOS:** comprueba el procesador en menú Apple → Acerca de este Mac, abre el DMG correspondiente, arrastra la aplicación a Aplicaciones y ábrela allí. Incluye el entorno necesario; no se requiere Python ni Homebrew.
- Los instaladores de Windows no tienen firma de editor. La aplicación Mac tiene firma ad-hoc, sin Developer ID ni certificación notarial de Apple. Verifica origen y SHA256. Si macOS la bloquea, intenta abrir una vez y busca Abrir igualmente en Ajustes del Sistema → Privacidad y seguridad. Confirma si se ofrece. No desactives Gatekeeper globalmente; consulta al administrador de un equipo gestionado.

## Primeros pasos

1. **Conecta un buzón.** Elige un proveedor o IMAP personalizado. Activa IMAP en el proveedor e introduce la contraseña de aplicación, código de autorización o token OAuth2 requerido. La aplicación incluye una guía paso a paso.
2. **Elige la IA.** Configura URL base, clave y modelo de una API compatible con Chat Completions, o usa Codex / DeepSeek Harness ya instalados y configurados. Harness no se incluye ni se descarga. No se incluye un servicio de IA gratuito. El modo API no requiere Codex.
3. **Elige la carpeta de informes e inicia la supervisión.** El intervalo predeterminado es de 60 segundos, ajustable entre 10 y 86400. Una comprobación sin novedades no llama a la IA.

**La primera comprobación de un buzón nuevo registra el punto de partida; no analiza todo el correo antiguo.** Después, al reanudar, se comprueban los mensajes recibidos durante pausas o apagados si siguen en la carpeta elegida.

## Idiomas y paquetes

La aplicación, el instalador y el desinstalador admiten **chino simplificado, inglés y español**. El primer inicio elige chino para un sistema chino, español para uno español e inglés para los demás. Puedes cambiarlo en Configuración general. En el instalador puedes elegir Descargar chino simplificado, Descargar inglés y Descargar español.

Si no está instalado el idioma elegido, aparece «No has descargado este idioma. ¿Quieres descargarlo ahora?». Confirma para descargar; cancelar o un fallo conserva el idioma actual. Los informes nuevos usan el idioma elegido y mantienen los seis requisitos del análisis; los anteriores no se traducen. El nombre en inglés es **Email Assistant** y en español **Asistente de correo electrónico**.

## Funciones

- Varias cuentas con preajustes y servidor, puerto, cifrado y proxy IMAP personalizables.
- Informes Markdown `.md` con vista previa; lectura de informes TXT antiguos.
- Informes organizados por buzón receptor, fecha y remitente; vista opcional de árbol además de la lista plana.
- Búsqueda local en cuerpo, remitente y nombres de adjuntos; filtros por fecha, remitente y presencia de adjuntos.
- Funcionamiento en bandeja del sistema o barra de menús; intervalo y carpeta de informes configurables.
- Actualizaciones dentro de la aplicación. Si hay varias fuentes, pruebas de velocidad limitadas eligen una ruta y se prueba otra si falla la red. Se verifica SHA256 antes de instalar y se solicita tu acción.
- Desinstalación con opciones independientes para conservar configuración e informes. Eliminar informes requiere otra confirmación.

El análisis de adjuntos depende del texto extraíble; las imágenes escaneadas y los documentos cifrados pueden no ser legibles. La búsqueda cubre el correo y los informes guardados localmente, no todo el buzón remoto.

### Carpetas y árbol de informes

Elige la carpeta raíz de informes en Configuración general, por ejemplo `Documentos/Correo`. Los informes siguen esta estructura:

```text
Correo/
└── 123@456.com/
    └── 2026-10-21/
        └── From 234@567.com/
            └── example-11-53.md
```

La primera carpeta identifica el buzón añadido que recibió el mensaje. Las fechas y las horas del nombre de archivo usan la hora de Pekín; las carpetas de remitentes usan direcciones de correo. Si no se conoce el buzón receptor o el remitente, se usan `unknown-account` y `From unknown-sender`, respectivamente. Los caracteres no válidos para nombres de archivo se sustituyen de forma segura.

Activa el árbol en Informes de correo para navegar por buzón → fecha → remitente → informe. Desactívalo para volver a la lista plana. Cambiar la vista no cambia la ubicación de los archivos.

Las carpetas de informes solo contienen informes. Los mensajes originales y los índices JSON se guardan en la carpeta de datos de la aplicación; los índices que las versiones anteriores dejaban junto a los informes se trasladan automáticamente. No hace falta borrarlos ni organizarlos a mano. Conservar los informes al desinstalar también conserva estos datos internos para seguir leyendo los originales y haciendo preguntas después de reinstalar.

## Proxy del correo

Cada buzón admite Directa, Proxy del sistema, HTTP CONNECT o SOCKS5. En los ajustes del buzón, abre Opciones avanzadas de conexión y proxy. Inicia v2rayN o tu aplicación de proxy e indica su dirección, puerto y protocolo reales; guarda y prueba. 10808 es solo un ejemplo. Un proxy explícito no requiere TUN.

Si falla el proxy, no se cambia silenciosamente a conexión directa. La opción se aplica a las pruebas IMAP y la recepción, no al tráfico de la API de IA. No se admiten PAC ni proxies con usuario y contraseña.

## Capturas

Son mensajes de prueba sintéticos, no correo de usuarios reales.

![Vista de informes de Windows](docs/images/windows.png)

![Vista de informes de Mac](docs/images/macos.png)

## Datos y límites

El servicio de IA elegido recibe el texto de los mensajes y el contenido legible de los adjuntos. Elige un servicio adecuado. Las credenciales usan la protección del sistema operativo; no publiques claves, tokens ni correo privado en incidencias. Probar la IA puede consumir saldo del proveedor. Los borradores deben revisarse antes de usarlos.

Los tokens OAuth2 se introducen y renuevan manualmente. Las pruebas de Windows se realizan en un ejecutor de GitHub; Intel Mac se verifica mediante Rosetta, no en un Mac Intel físico.

## Guías y desarrollo

| Plataforma | Guía | Desarrollo |
| --- | --- | --- |
| Windows | [Español](windows/README.es.md) / [English](windows/README.en.md) / [中文](windows/README.md) | [Compilación y pruebas](windows/docs/DEVELOPMENT.md) |
| macOS | [Español](macos/README.es.md) / [English](macos/README.en.md) / [中文](macos/README.md) | [Compilación y pruebas](macos/docs/DEVELOPMENT.md) |

Guías del correo: [Windows](windows/docs/Mail-account-setup-es.txt) y [Mac](macos/Resources/Mail-account-setup-es.txt), con instrucciones completas para cada proveedor, proxy y los 20 pasos OAuth2 de Microsoft.

El código está en `windows/` y `macos/`. Código, documentación, paquetes de idioma e instaladores se mantienen en este repositorio: [Benson-YiYan/benson-mail-assistant](https://github.com/Benson-YiYan/benson-mail-assistant). Manifiesto estable: [`distribution/manifest.json`](distribution/manifest.json). Las publicaciones indican las versiones y el alcance de las verificaciones de cada paquete.

[Notificar un problema](https://github.com/Benson-YiYan/benson-mail-assistant/issues): incluye sistema operativo, versión y error sin datos privados. Si te ahorra tiempo, una ⭐ es bienvenida.

La dirección antigua `benson-mail-updates/main/manifest.json` sigue disponible. El servidor sincroniza allí el mismo manifiesto para que las versiones antiguas puedan buscar y descargar actualizaciones. El repositorio adicional `benson-mail-updates` solo contiene esta entrada de compatibilidad. Si falla la búsqueda, aparece el botón «Descargar la última versión desde GitHub». Instalar sobre la versión existente conserva la configuración del correo y de IA y los informes.

## Volver a resumir y preguntar sobre un correo

Selecciona un informe y elige Volver a resumir para generar las seis secciones en el idioma actual de la interfaz. Si falla, se conserva el informe anterior. Se utiliza el índice guardado del correo; los informes antiguos sin ese índice muestran una explicación.

Preguntar sobre este correo permite preguntas de seguimiento y archivos adicionales mediante el selector. Cada correo conserva su propia conversación para continuar después. Los hechos se basan en el correo original y sus adjuntos legibles. Se incluye la conversación, pero los informes generados, respuestas anteriores y resúmenes comprimidos no son pruebas de hechos. Si crece demasiado, se resumen los turnos antiguos, se mantienen los recientes y se indica la compresión. El resumen no conserva cada palabra; el historial completo permanece guardado localmente. Cita y verifica cifras o frases importantes.

Estas acciones utilizan la IA configurada y pueden generar costes. Los archivos adicionales se leen solo para extraer texto; los archivos ilegibles o demasiado grandes producen un error explícito. No se envían correos. El historial se guarda en los datos locales de la aplicación. Se elimina al desinstalar, aunque conserves la configuración del correo y de IA; copia antes las conversaciones que necesites.

## Reglas de remitentes y correo no deseado

En Buzones y comprobación → Bloquear correos, elige una lista negra o una lista blanca. Se omiten los remitentes de la lista negra; la lista blanca solo permite resumir los remitentes incluidos. Una lista blanca vacía omite todos los correos nuevos. Las reglas se aplican a todos los buzones y comparan direcciones completas sin distinguir mayúsculas. Puedes añadir, seleccionar en lote o quitar direcciones.

«No resumir correo no deseado (algunos proveedores pueden no admitirlo)» utiliza marcas explícitas del servidor, cabeceras o carpetas de correo no deseado. No adivina por el asunto ni llama a la IA para clasificarlo. Solo se comprueba la carpeta configurada; sin indicadores del proveedor no se puede identificar. La opción está desactivada por defecto.

Los mensajes omitidos se agrupan por remitente en los registros locales. Puedes resumir uno o varios con el idioma y la IA actuales. Es una excepción para esa ocasión y no cambia las reglas; los fallos conservan el registro. Eliminar registro solo borra el registro local, nunca el correo original. Las reglas afectan a los mensajes nuevos comprobados y no eliminan informes existentes.

Arrastra el divisor entre el informe y la conversación del correo para ajustar el tamaño de ambas áreas.

## Nuevos flujos y mejoras de fiabilidad

- **Borradores de respuesta:** elige tono, idioma e instrucciones, edita destinatario, asunto y cuerpo y guarda localmente o copia. La aplicación nunca envía el borrador automáticamente.
- **Lectura mejorada de adjuntos:** las imágenes y los PDF escaneados usan primero OCR nativo local; el texto extraído se envía a la IA seleccionada. Hay límites de idioma del sistema, tamaño y calidad; se informa del contenido ilegible y no se garantiza el reconocimiento.
- **Correos históricos:** selecciona buzón y fechas, consulta la cantidad pendiente y confirma para añadirlos a la cola. Puede generar costes de IA y respeta las reglas de remitentes y spam.
- **Fuentes y preguntas continuas:** consulta el correo original guardado, el texto extraído y sus limitaciones. Las preguntas usan el correo original y sus adjuntos legibles como evidencia; los informes generados y las respuestas anteriores no sustituyen los originales. Se avisa si faltan fuentes de correos antiguos.
- **Notificaciones y horario silencioso:** pausa las notificaciones del sistema independientemente de la supervisión. Durante el horario silencioso, incluso de noche, se siguen comprobando correos y guardando informes.
- **Diagnóstico:** exporta manualmente información operativa sin datos sensibles para resolver problemas; no incluye claves, cuerpos, adjuntos ni conversaciones.
- **Un guardado por página:** los cambios de buzón, IA y Ajustes generales se aplican al guardar su página. Salir con cambios pendientes pide confirmación. El idioma, la carpeta de informes y el inicio de sesión se gestionan en Ajustes generales.
- **Descargas en Windows:** Ajustes generales tiene su propia página. Más tarde cierra el diálogo y mantiene la descarga y su progreso en segundo plano; solo Cancelar la detiene. Las interrupciones permiten reintentar o reanudar; se verifican tamaño y SHA256 y la instalación requiere tu acción.

| Guías completas | 简体中文 | English | Español |
| --- | --- | --- | --- |
| Mac | [中文](macos/Resources/Quick-start-zh.txt) | [English](macos/Resources/Quick-start-en.txt) | [Español](macos/Resources/Quick-start-es.txt) |
| Windows | [中文](windows/docs/Quick-start-zh.txt) | [English](windows/docs/Quick-start-en.txt) | [Español](windows/docs/Quick-start-es.txt) |

## Guía completa de funciones y ajustes

Pasos de acceso a todas las funciones y ajustes:

- [Mac](macos/Resources/Quick-start-es.txt)
- [Windows](windows/docs/Quick-start-es.txt)

## Origen de los costes y saldos de cuenta

Abre los registros de uso desde la configuración de IA para ver los tokens de entrada/salida, los costes informados por el proveedor, las estimaciones locales y las llamadas cubiertas por cada origen. El coste del proveedor tiene prioridad por llamada; esa llamada no se incluye en la estimación local. Si falta el coste, se estima con los precios guardados y el uso de tokens; sin datos suficientes se muestra Desconocido. Las monedas se mantienen separadas y no se inventan ni recalculan importes históricos.

El `usage.cost` oficial de OpenRouter se registra en USD. Una API compatible debe devolver explícitamente `usage.cost` con `cost_currency`, o un objeto cost con `amount` y `currency`. Los demás proveedores siguen usando estimaciones. El importe informado no sustituye a la factura final.

Consultar saldo de cuenta solo se ejecuta al pulsar el botón, admite los endpoints oficiales de DeepSeek y OpenRouter y no genera contenido de IA. El saldo pertenece a toda la cuenta y puede incluir otras aplicaciones; sus cambios no se atribuyen a esta aplicación. OpenRouter exige permisos de administración para consultar el saldo, por lo que puede rechazar una clave normal de inferencia. No sustituyas esa clave por una de administración solo para consultar el saldo. Un error no se presenta como saldo cero.

Tras descargar y verificar la actualización con SHA256, la aplicación pregunta si deseas instalar y reiniciar. Elegir Más tarde conserva el paquete verificado para instalarlo sin volver a descargarlo.
