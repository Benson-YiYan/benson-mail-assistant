using Microsoft.UI.Xaml.Media;

namespace BensonMail;

internal static class MailTypography
{
    // Prefer the Windows Chinese UI face for this Chinese-language application.
    // Put it first so Segoe's automatic glyph fallback cannot select another CJK face.
    internal const string FontStack = "Microsoft YaHei UI, Microsoft YaHei, Segoe UI Variable, Segoe UI";
    internal static readonly FontFamily Font = Create();
    static FontFamily Create()
    {
        Program.Trace("Creating Windows font family");
        var family = new FontFamily(FontStack);
        Program.Trace("Windows font family created");
        return family;
    }
}
