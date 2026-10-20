using System.Collections.Generic;

namespace BensonMail;

// Recovery for previously downloaded language packs that predate sender controls.
internal static class SenderPolicyLocalization
{
    static readonly Dictionary<string, (string en, string es)> labels = new() {
        ["拖动调整报告与聊天区域"] = ("Drag to resize the report and chat panes", "Arrastra para ajustar el informe y el chat"),
        ["不在白名单"] = ("Not on the allowlist", "No está en la lista de permitidos"),
        ["不总结垃圾邮件（部分邮箱可能不支持）"] = ("Do not summarize spam (some providers may not support this)", "No resumir correo no deseado (algunos proveedores pueden no admitirlo)"),
        ["从发件人中批量选择"] = ("Select multiple senders", "Seleccionar varios remitentes"),
        ["保存屏蔽设置"] = ("Save blocking settings", "Guardar configuración de bloqueo"),
        ["全选记录"] = ("Select all records", "Seleccionar todos los registros"),
        ["删除本地跳过记录？"] = ("Delete local skip records?", "¿Borrar registros locales de omisión?"),
        ["删除此记录"] = ("Delete this record", "Borrar este registro"),
        ["删除记录"] = ("Delete records", "Borrar registros"),
        ["删除选中记录"] = ("Delete selected records", "Borrar registros seleccionados"),
        ["刷新屏蔽记录"] = ("Refresh skipped records", "Actualizar registros omitidos"),
        ["发件人邮箱地址"] = ("Sender email address", "Dirección de correo del remitente"),
        ["取消"] = ("Cancel", "Cancelar"),
        ["取消选择"] = ("Clear selection", "Quitar selección"),
        ["只删除选中的本地记录，不会删除邮箱服务器上的邮件。"] = ("Only the selected local records will be deleted. Emails on the mail server will remain.", "Solo se borrarán los registros locales seleccionados. Los correos del servidor se conservarán."),
        ["名单中的邮箱地址"] = ("Addresses on the list", "Direcciones de la lista"),
        ["名单为空。"] = ("The list is empty.", "La lista está vacía."),
        ["名单模式"] = ("List mode", "Modo de lista"),
        ["命中黑名单"] = ("On the blocklist", "Está en la lista de bloqueo"),
        ["垃圾邮件"] = ("Spam", "Correo no deseado"),
        ["垃圾邮件选项无效。"] = ("Invalid spam option.", "Opción de correo no deseado no válida."),
        ["屏蔽规则无效。"] = ("Invalid blocking rules.", "Reglas de bloqueo no válidas."),
        ["屏蔽邮件"] = ("Blocked emails", "Correos bloqueados"),
        ["已加入总结队列。"] = ("Added to the summary queue.", "Añadido a la cola de resumen."),
        ["已加入总结队列；开始监听后会处理。"] = ("Added to the summary queue. Start monitoring to process it.", "Añadido a la cola de resumen. Inicia la supervisión para procesarlo."),
        ["已跳过的邮件"] = ("Skipped emails", "Correos omitidos"),
        ["总结失败，可重试"] = ("Summary failed; you can retry", "Falló el resumen; puedes reintentarlo"),
        ["总结此邮件"] = ("Summarize this email", "Resumir este correo"),
        ["总结选中邮件"] = ("Summarize selected emails", "Resumir correos seleccionados"),
        ["无主题"] = ("No subject", "Sin asunto"),
        ["正在处理…"] = ("Working…", "Trabajando…"),
        ["正在总结"] = ("Summarizing", "Resumiendo"),
        ["正在总结选中邮件…"] = ("Summarizing selected emails…", "Resumiendo los correos seleccionados…"),
        ["此设置适用于所有已配置邮箱。黑名单跳过名单内的发件人；白名单只总结名单内的发件人。"] = ("Applies to all configured mailboxes. A blocklist skips listed senders; an allowlist summarizes only listed senders.", "Se aplica a todos los buzones configurados. La lista de bloqueo omite los remitentes indicados; la lista de permitidos solo resume los indicados."),
        ["添加"] = ("Add", "Añadir"),
        ["添加地址"] = ("Add address", "Añadir dirección"),
        ["添加选中地址"] = ("Add selected addresses", "Añadir direcciones seleccionadas"),
        ["白名单"] = ("Allowlist", "Lista de permitidos"),
        ["白名单：只有名单中的发件人会自动总结。空白名单会跳过所有发件人。"] = ("Allowlist: only listed senders are summarized automatically. An empty list skips all senders.", "Lista de permitidos: solo se resumen automáticamente los remitentes indicados. Una lista vacía omite a todos."),
        ["移除选中地址"] = ("Remove selected addresses", "Quitar direcciones seleccionadas"),
        ["等待总结"] = ("Waiting to summarize", "En espera de resumen"),
        ["请输入邮箱地址。"] = ("Enter an email address.", "Introduce una dirección de correo."),
        ["请选择邮件记录。"] = ("Select email records.", "Selecciona registros de correo."),
        ["请选择黑名单或白名单。"] = ("Choose a blocklist or allowlist.", "Elige una lista de bloqueo o de permitidos."),
        ["还没有已知发件人，可以先手动添加地址。"] = ("No known senders yet. You can add an address manually.", "Aún no hay remitentes conocidos. Puedes añadir una dirección manualmente."),
        ["还没有被跳过的邮件。"] = ("No emails have been skipped yet.", "Todavía no se ha omitido ningún correo."),
        ["这里只保存本地跳过记录；删除记录不会删除邮箱服务器上的邮件。"] = ("Only local skip records are stored here. Deleting a record does not delete the email from the mail server.", "Aquí solo se guardan registros locales de omisión. Borrar un registro no elimina el correo del servidor."),
        ["邮件正在总结，请完成后再删除记录。"] = ("This email is being summarized. Wait until it finishes before deleting its record.", "Este correo se está resumiendo. Espera a que termine antes de borrar su registro."),
        ["邮箱地址列表无效。"] = ("Invalid email address list.", "Lista de direcciones de correo no válida."),
        ["黑名单"] = ("Blocklist", "Lista de bloqueo"),
        ["黑名单：名单中的发件人不自动总结，其他发件人照常处理。"] = ("Blocklist: listed senders are not summarized automatically. Other senders are handled normally.", "Lista de bloqueo: no se resumen automáticamente los remitentes indicados. Los demás se procesan normalmente."),
    };
    internal static string? Translate(string value, string code)
    {
        if (labels.TryGetValue(value, out var label)) return code == "es" ? label.es : label.en;
        const string addressPrefix = "请输入完整的邮箱地址：";
        if (value.StartsWith(addressPrefix, System.StringComparison.Ordinal))
            return (code == "es" ? "Introduce una dirección de correo completa: " : "Enter a complete email address: ") + value[addressPrefix.Length..];
        return null;
    }
}
