import Foundation

/// Small fallback for newly introduced controls when an already-installed pack predates them.
/// These strings do not install or activate any optional language pack.
enum SenderPolicyLocalization {
    private static let english: [String: String] = [
        "DNS 解析失败，请检查域名和 DNS 设置": "DNS lookup failed; check the hostname and DNS settings",
        "TLS 证书验证失败，请检查电脑时间、代理或服务商证书": "TLS certificate verification failed; check the system clock, proxy, or provider certificate",
        "不总结垃圾邮件": "Do not summarize spam",
        "不总结垃圾邮件（部分邮箱可能不支持）": "Do not summarize spam (some mail providers may not support this)",
        "仅依据邮箱服务商的垃圾邮件标记；不会凭主题或正文猜测。": "Uses explicit spam flags from your mail provider; never guesses from the subject or body.",
        "仅删除本地跳过记录，不会删除邮箱中的邮件。总结一次不会把发件人移出名单。": "Deleting removes only the local skipped record, never mailbox messages. A one-time summary keeps the sender rule.",
        "从已有发件人批量选择": "Select from known senders",
        "保存屏蔽规则": "Save mail rules",
        "全选": "Select all",
        "删除所选记录": "Delete selected records",
        "删除记录": "Delete record",
        "发件人不在白名单中": "Sender is not on the allowlist",
        "发件人在黑名单中": "Sender is on the blocklist",
        "发件人规则": "Sender rules",
        "取消选择": "Clear selection",
        "只总结白名单中的发件人；名单为空时会跳过所有邮件。": "Only summarize mail from allowlisted senders. An empty list skips all mail.",
        "垃圾邮件选项无效。": "The spam option is invalid.",
        "尚未添加邮箱地址": "No email addresses added yet",
        "屏蔽规则已保存。": "Mail rules saved.",
        "屏蔽规则无效。": "The mail rules are invalid.",
        "屏蔽邮件": "Blocked mail",
        "已加入一次性总结队列": "Queued for a one-time summary",
        "总结一次": "Summarize once",
        "总结所选邮件一次": "Summarize selected mail once",
        "所选邮件已加入一次性总结队列，不会改变屏蔽规则。": "Selected mail was queued for a one-time summary. Sender rules are unchanged.",
        "批量操作": "Batch actions",
        "有未保存的屏蔽规则": "Mail rules have unsaved changes",
        "服务器或代理拒绝连接，请检查地址、端口及代理是否运行": "The server or proxy refused the connection; check the address, port, and proxy",
        "本地记录已删除，邮箱中的原邮件未删除。": "Local records deleted. Original mailbox messages were kept.",
        "正在处理屏蔽规则…": "Updating mail rules…",
        "正在总结…": "Summarizing…",
        "没有可添加的已有发件人": "No known senders to add",
        "没有被跳过的邮件": "No skipped mail",
        "添加": "Add",
        "添加后请保存屏蔽规则。": "Save the mail rules after adding addresses.",
        "添加邮箱地址": "Add email addresses",
        "白名单": "Allowlist",
        "被跳过的邮件": "Skipped mail",
        "被跳过邮件记录过大，请稍后重试。": "The skipped-mail data is too large. Please try again later.",
        "规则对所有已添加的邮箱生效；跳过的邮件不会调用 AI，也不会从邮箱删除。": "Rules apply to every added account. Skipped mail uses no AI and remains in your mailbox.",
        "请选择邮件记录。": "Select mail records.",
        "请选择黑名单或白名单。": "Choose the blocklist or allowlist.",
        "跳过黑名单中的发件人，其余邮件正常总结。": "Skip blocklisted senders and summarize other mail normally.",
        "连接失败，请检查网络、代理和基础地址": "Connection failed; check the network, proxy, and base URL",
        "连接或读取超时（最长等待 120 秒）": "Connection or read timed out (120-second maximum wait)",
        "选择邮件": "Select message",
        "邮件正在总结，请完成后再删除记录。": "This message is being summarized. Wait before deleting its record.",
        "邮件规则操作失败，请重试。": "The mail rule operation failed. Please try again.",
        "邮箱地址列表无效。": "The email address list is invalid.",
        "邮箱标记为垃圾邮件": "Marked as spam by the mail provider",
        "黑名单": "Blocklist",
    ]
    private static let spanish: [String: String] = [
        "DNS 解析失败，请检查域名和 DNS 设置": "Falló la consulta DNS; revisa el nombre del servidor y la configuración DNS",
        "TLS 证书验证失败，请检查电脑时间、代理或服务商证书": "Falló la verificación del certificado TLS; revisa la hora del sistema, el proxy o el certificado del proveedor",
        "不总结垃圾邮件": "No resumir el correo no deseado",
        "不总结垃圾邮件（部分邮箱可能不支持）": "No resumir el correo no deseado (algunos proveedores podrían no admitirlo)",
        "仅依据邮箱服务商的垃圾邮件标记；不会凭主题或正文猜测。": "Usa las marcas explícitas de correo no deseado del proveedor; no lo deduce del asunto ni del contenido.",
        "仅删除本地跳过记录，不会删除邮箱中的邮件。总结一次不会把发件人移出名单。": "Eliminar solo borra el registro local, nunca el mensaje del buzón. Resumir una vez mantiene la regla del remitente.",
        "从已有发件人批量选择": "Seleccionar entre remitentes conocidos",
        "保存屏蔽规则": "Guardar reglas de correo",
        "全选": "Seleccionar todo",
        "删除所选记录": "Eliminar los registros seleccionados",
        "删除记录": "Eliminar registro",
        "发件人不在白名单中": "El remitente no está en la lista de permitidos",
        "发件人在黑名单中": "El remitente está en la lista de bloqueo",
        "发件人规则": "Reglas de remitentes",
        "取消选择": "Borrar selección",
        "只总结白名单中的发件人；名单为空时会跳过所有邮件。": "Solo resume los mensajes de remitentes permitidos. Una lista vacía omite todos los mensajes.",
        "垃圾邮件选项无效。": "La opción de correo no deseado no es válida.",
        "尚未添加邮箱地址": "Todavía no se han añadido direcciones",
        "屏蔽规则已保存。": "Reglas de correo guardadas.",
        "屏蔽规则无效。": "Las reglas de correo no son válidas.",
        "屏蔽邮件": "Correo bloqueado",
        "已加入一次性总结队列": "En cola para resumir una vez",
        "总结一次": "Resumir una vez",
        "总结所选邮件一次": "Resumir los mensajes seleccionados una vez",
        "所选邮件已加入一次性总结队列，不会改变屏蔽规则。": "Los mensajes seleccionados están en cola para resumirse una vez. Las reglas no han cambiado.",
        "批量操作": "Acciones en lote",
        "有未保存的屏蔽规则": "Hay cambios sin guardar en las reglas",
        "服务器或代理拒绝连接，请检查地址、端口及代理是否运行": "El servidor o el proxy rechazó la conexión; revisa la dirección, el puerto y el proxy",
        "本地记录已删除，邮箱中的原邮件未删除。": "Se eliminaron los registros locales. Se conservaron los mensajes originales del buzón.",
        "正在处理屏蔽规则…": "Actualizando las reglas de correo…",
        "正在总结…": "Resumiendo…",
        "没有可添加的已有发件人": "No hay remitentes conocidos que añadir",
        "没有被跳过的邮件": "No hay mensajes omitidos",
        "添加": "Añadir",
        "添加后请保存屏蔽规则。": "Guarda las reglas después de añadir las direcciones.",
        "添加邮箱地址": "Añadir direcciones de correo",
        "白名单": "Lista de permitidos",
        "被跳过的邮件": "Mensajes omitidos",
        "被跳过邮件记录过大，请稍后重试。": "Los datos de mensajes omitidos son demasiado grandes. Inténtalo de nuevo más tarde.",
        "规则对所有已添加的邮箱生效；跳过的邮件不会调用 AI，也不会从邮箱删除。": "Las reglas se aplican a todas las cuentas añadidas. Los mensajes omitidos no usan IA y permanecen en el buzón.",
        "请选择邮件记录。": "Selecciona registros de mensajes.",
        "请选择黑名单或白名单。": "Elige la lista de bloqueo o de permitidos.",
        "跳过黑名单中的发件人，其余邮件正常总结。": "Omite los remitentes bloqueados y resume los demás mensajes normalmente.",
        "连接失败，请检查网络、代理和基础地址": "Error de conexión; revisa la red, el proxy y la URL base",
        "连接或读取超时（最长等待 120 秒）": "Se agotó el tiempo de conexión o lectura (espera máxima de 120 segundos)",
        "选择邮件": "Seleccionar mensaje",
        "邮件正在总结，请完成后再删除记录。": "Se está resumiendo el mensaje. Espera antes de eliminar el registro.",
        "邮件规则操作失败，请重试。": "No se pudo completar la operación de reglas. Inténtalo de nuevo.",
        "邮箱地址列表无效。": "La lista de direcciones de correo no es válida.",
        "邮箱标记为垃圾邮件": "El proveedor lo marcó como correo no deseado",
        "黑名单": "Lista de bloqueo",
    ]
    static var keys: Set<String> { Set(english.keys).union(spanish.keys) }
    static func translate(_ text: String, language: String) -> String? {
        guard ["en", "es"].contains(language) else { return nil }
        let dictionary = language == "es" ? spanish : english
        if let result = dictionary[text] { return result }
        let addressPrefix = "请输入完整的邮箱地址："
        if text.hasPrefix(addressPrefix) {
            return (language == "es" ? "Introduce una dirección de correo completa: " : "Enter a complete email address: ") + text.dropFirst(addressPrefix.count)
        }
        if text.hasPrefix("AI 接口"), let marker = text.range(of: "。\n具体原因：") {
            let hint = String(text[text.index(text.startIndex, offsetBy: "AI 接口".count)..<marker.lowerBound])
            if let localized = dictionary[hint] {
                return (language == "es" ? "Problema de conexión con la IA: " : "AI connection issue: ") + localized + ".\n" + (language == "es" ? "Detalles: " : "Details: ") + text[marker.upperBound...]
            }
        }
        return nil
    }
}
