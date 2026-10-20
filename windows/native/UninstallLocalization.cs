using System;
using System.Collections.Generic;

namespace BensonMail;

// Essential removal controls remain available offline even when no optional application language pack was installed.
// This deliberately covers only the uninstaller; application interfaces and guides are downloaded language packs.
internal static class UninstallLocalization
{
    static readonly Dictionary<string, (string en, string es)> Labels = new() {
        ["\n仅删除可识别的报告和邮件索引，保留其他文件及自选根目录。"] = ("\nOnly recognized reports and mail indexes are deleted. Other files and your chosen root folder are retained.", "\nSolo se eliminan los informes reconocidos y sus índices. Se conservan los demás archivos y la carpeta principal elegida."),
        ["\n其他文件及自选根目录会保留。此操作无法撤销。"] = ("\nOther files and your chosen root folder will remain. This cannot be undone.", "\nSe conservarán los demás archivos y la carpeta principal elegida. Esta acción no se puede deshacer."),
        ["\n同时删除已选的邮件报告。"] = ("\nAlso delete the selected mail reports.", "\nEliminar también los informes de correo seleccionados."),
        ["\n已生成的邮件报告保留。"] = ("\nKeep generated mail reports.", "\nConservar los informes de correo generados."),
        ["\n数据目录："] = ("\nData folder: ", "\nCarpeta de datos: "),
        ["保留账号列表、服务器、AI 设置及加密密钥，供本机同一 Windows 用户重装后继续使用。"] = ("Keep accounts, servers, AI settings, and encrypted credentials for reinstallation by the same Windows user on this computer.", "Conservar cuentas, servidores, configuración de IA y credenciales cifradas para reinstalar con el mismo usuario de Windows en este equipo."),
        ["保留邮件报告"] = ("Keep email reports", "Conservar informes de correo"),
        ["保留邮箱及 AI 配置，移除程序和缓存。"] = ("Keep email and AI settings; remove the app and cache.", "Conservar la configuración del correo y de la IA; eliminar la aplicación y la caché."),
        ["保留配置"] = ("Keep configuration", "Conservar configuración"),
        ["准备就绪"] = ("Ready", "Preparado"),
        ["准备就绪。可选择保留配置，方便下次安装。"] = ("Ready. You may keep settings for the next installation.", "Preparado. Puedes conservar la configuración para la próxima instalación."),
        ["删除报告并卸载"] = ("Delete reports and uninstall", "Eliminar informes y desinstalar"),
        ["卸载"] = ("Uninstall", "Desinstalar"),
        ["卸载会通过独立组件执行，进度显示在此处。"] = ("An independent helper performs the uninstall; progress appears here.", "Un componente independiente realiza la desinstalación; el progreso aparece aquí."),
        ["卸载完成。程序、配置、加密密钥和缓存已清理。"] = ("Uninstalled. The app, settings, encrypted credentials, and cache were removed.", "Desinstalado. Se eliminaron la aplicación, la configuración, las credenciales cifradas y la caché."),
        ["卸载完成。邮箱及 AI 配置已保留，下次重装可继续使用。"] = ("Uninstalled. Email and AI settings were kept for reinstallation.", "Desinstalado. Se conservó la configuración del correo y de la IA para reinstalar."),
        ["卸载未完成："] = ("Uninstall incomplete: ", "Desinstalación incompleta: "),
        ["卸载组件未能完成，请关闭占用文件的程序后重试。"] = ("The uninstall component did not finish. Close programs using its files and retry.", "El componente de desinstalación no terminó. Cierra los programas que utilicen sus archivos y vuelve a intentarlo."),
        ["卸载邮件小秘书"] = ("Uninstall Email Assistant", "Desinstalar Asistente de correo electrónico"),
        ["取消"] = ("Cancel", "Cancelar"),
        ["否"] = ("No", "No"),
        ["处理中，请稍候…"] = ("Working. Please wait…", "Trabajando. Espera…"),
        ["完成"] = ("Done", "Listo"),
        ["将先停止邮箱监听并退出程序，再继续卸载确认。选择“否”或“取消”不会卸载。"] = ("Email monitoring will stop and the app will close before the uninstall confirmation. No or Cancel leaves the app and files unchanged.", "La supervisión del correo se detendrá y la aplicación se cerrará antes de confirmar la desinstalación. No o Cancelar deja la aplicación y los archivos sin cambios."),
        ["将删除以下目录中本软件可识别的邮件报告及索引：\n"] = ("Recognized Email Assistant reports and indexes will be deleted from:\n", "Se eliminarán los informes e índices reconocidos de Asistente de correo electrónico de:\n"),
        ["已完成"] = ("Completed", "Completado"),
        ["已将程序或数据目录中的报告保留到："] = ("Reports from the app or data folder were retained at: ", "Los informes de la carpeta de la aplicación o de datos se conservaron en: "),
        ["开启＝保留；关闭＝删除。"] = ("On = keep; off = delete.", "Activado = conservar; desactivado = eliminar."),
        ["报告保留位置仍位于待卸载目录中，请先修改报告保存位置。"] = ("The retained report location is inside the folder being removed. Change the report folder first.", "La ubicación de los informes conservados está dentro de la carpeta que se eliminará. Cambia primero la carpeta de informes."),
        ["报告目录："] = ("Report folder: ", "Carpeta de informes: "),
        ["报告默认保留；关闭“保留邮件报告”才会删除可识别的报告及索引。"] = ("Reports are kept by default. Turn off “Keep email reports” to delete recognized reports and indexes.", "Los informes se conservan de forma predeterminada. Desactiva «Conservar informes de correo» para eliminar los informes reconocidos y sus índices."),
        ["无法启动卸载组件。"] = ("Could not start the uninstall component.", "No se pudo iniciar el componente de desinstalación."),
        ["无法确认原卸载程序已退出，请关闭后重试。"] = ("Could not confirm that the original uninstaller exited. Close it and retry.", "No se pudo confirmar que se cerrara el desinstalador original. Ciérralo y vuelve a intentarlo."),
        ["是，退出并继续"] = ("Yes, close and continue", "Sí, cerrar y continuar"),
        ["未能完成"] = ("Could not finish", "No se pudo completar"),
        ["未配置"] = ("Not configured", "Sin configurar"),
        ["检测到邮件小秘书正在运行，是否退出？"] = ("Email Assistant is running. Would you like to close it?", "Asistente de correo electrónico está en ejecución. ¿Quieres cerrarlo?"),
        ["正在保留邮箱及 AI 配置、清理缓存…"] = ("Keeping email and AI settings and clearing cache…", "Conservando la configuración del correo y de la IA y borrando la caché…"),
        ["正在准备…"] = ("Preparing…", "Preparando…"),
        ["正在删除程序目录…"] = ("Removing the app folder…", "Eliminando la carpeta de la aplicación…"),
        ["正在删除选中的邮件报告…"] = ("Deleting selected mail reports…", "Eliminando los informes de correo seleccionados…"),
        ["正在清理指向本次安装的快捷方式…"] = ("Removing shortcuts for this installation…", "Eliminando accesos directos de esta instalación…"),
        ["正在清理自启动注册表项…"] = ("Removing startup registry entries…", "Eliminando entradas de inicio del Registro…"),
        ["正在清理配置、加密密钥和缓存…"] = ("Removing settings, encrypted credentials, and cache…", "Eliminando configuración, credenciales cifradas y caché…"),
        ["正在等待邮件小秘书退出…"] = ("Waiting for Email Assistant to close…", "Esperando a que se cierre Asistente de correo electrónico…"),
        ["正在读取卸载信息…"] = ("Loading uninstall information…", "Cargando información de desinstalación…"),
        ["测试模式只允许专用临时夹具目录。"] = ("Test mode only permits dedicated temporary fixture folders.", "El modo de prueba solo permite carpetas temporales específicas para pruebas."),
        ["独立卸载进程仍在程序目录中，已停止删除。"] = ("The independent helper is still inside the app folder. Deletion was stopped.", "El componente independiente sigue dentro de la carpeta de la aplicación. Se detuvo la eliminación."),
        ["确认删除邮件报告？"] = ("Delete email reports?", "¿Eliminar los informes de correo?"),
        ["确认卸载？"] = ("Confirm uninstall?", "¿Confirmar la desinstalación?"),
        ["移除程序、配置、加密密钥和缓存。"] = ("Remove the app, settings, encrypted credentials, and cache.", "Eliminar la aplicación, la configuración, las credenciales cifradas y la caché."),
        ["程序目录名称或结构不符，请手动删除当前解压文件夹。"] = ("The app folder name or structure is unexpected. Delete the extracted folder manually.", "El nombre o la estructura de la carpeta de la aplicación no son los esperados. Elimina manualmente la carpeta extraída."),
        ["程序目录："] = ("Application folder: ", "Carpeta de la aplicación: "),
        ["程序目录：模拟安装目录"] = ("Application folder: simulated installation", "Carpeta de la aplicación: instalación simulada"),
        ["等待原卸载程序退出超时，尚未删除程序目录。"] = ("Timed out waiting for the original uninstaller. The app folder has not been deleted.", "Se agotó el tiempo de espera del desinstalador original. No se eliminó la carpeta de la aplicación."),
        ["缓存和收信进度会清除，重装后重新记录收信起点。自启动项及本次安装的快捷方式会移除。"] = ("Cache and mail progress will be cleared. Reinstallation establishes a new baseline. Startup entries and this installation's shortcuts will be removed.", "Se borrarán la caché y el progreso del correo. La reinstalación establecerá una nueva referencia inicial. Se eliminarán las entradas de inicio y los accesos directos de esta instalación."),
        ["若邮件小秘书正在运行，点击卸载后会询问是否退出；确认退出后再继续。"] = ("If Email Assistant is running, Uninstall will ask to close it before continuing.", "Si Asistente de correo electrónico está en ejecución, el desinstalador pedirá cerrarlo antes de continuar."),
        ["邮件"] = ("Mail", "Correo"),
        ["邮件小秘书"] = ("Email Assistant", "Asistente de correo electrónico"),
        ["部分目录仍然存在，请关闭占用它们的程序后重试。"] = ("Some folders remain. Close programs using them and retry.", "Quedan algunas carpetas. Cierra los programas que las utilicen y vuelve a intentarlo."),
    };
    internal static string? Translate(string value, string code)
    {
        if (code is not ("en" or "es")) return null;
        if (Labels.TryGetValue(value, out var label)) return code == "es" ? label.es : label.en;
        foreach (var pair in Labels) {
            if (pair.Key.EndsWith("：", StringComparison.Ordinal) && value.StartsWith(pair.Key, StringComparison.Ordinal))
                return (code == "es" ? pair.Value.es : pair.Value.en) + value[pair.Key.Length..];
        }
        return null;
    }
}
