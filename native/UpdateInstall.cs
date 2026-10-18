using System;
using System.Diagnostics;
using System.IO;

namespace BensonMail;

static class UpdateInstall
{
    internal static ProcessStartInfo StartInfo(VerifiedUpdate update, string installDirectory, string language, int pid)
    {
        if (!Path.IsPathFullyQualified(update.Path) || Path.GetExtension(update.Path) != ".exe") throw new InvalidDataException("Invalid installer path.");
        var start = new ProcessStartInfo(update.Path) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(update.Path)! };
        start.ArgumentList.Add("/UPDATE=1");
        start.ArgumentList.Add("/UPDATEPID=" + pid);
        start.ArgumentList.Add("/DIR=" + Path.TrimEndingDirectorySeparator(installDirectory));
        start.ArgumentList.Add("/LANG=" + (language == "zh" ? "chinesesimp" : "english"));
        start.ArgumentList.Add("/NORESTART");
        return start;
    }
}
