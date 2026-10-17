using Microsoft.UI.Xaml.Media;

namespace BensonMail;

internal static class MailTypography
{
    // Use the Windows 11 Latin UI face and Windows' Chinese UI face.
    // Segoe UI remains available on Windows 10; no third-party fonts are bundled.
    internal const string FontStack = "Segoe UI Variable, Segoe UI, Microsoft YaHei UI, Microsoft YaHei";
    internal static readonly FontFamily Font = Create();
    static FontFamily Create()
    {
        Program.Trace("Creating Windows font family");
        var family = new FontFamily(FontStack);
        Program.Trace("Windows font family created");
        return family;
    }
}
