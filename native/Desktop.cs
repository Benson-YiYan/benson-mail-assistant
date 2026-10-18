using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace BensonMail;

// WinUI uses the Windows shell directly; no Windows Forms desktop runtime is needed.
internal static class Desktop
{
    [StructLayout(LayoutKind.Sequential)] struct HighContrastData { public uint Size, Flags; public IntPtr Scheme; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool SystemParametersInfoW(uint action, uint size, ref HighContrastData value, uint flags);
    [DllImport("user32.dll", EntryPoint = "SystemParametersInfoW")] static extern bool SystemParametersInfoBool(uint action, uint size, out int value, uint flags);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int MessageBoxW(IntPtr window, string text, string caption, uint flags);
    internal static bool HighContrast { get { var value = new HighContrastData { Size = (uint)Marshal.SizeOf<HighContrastData>() }; return SystemParametersInfoW(0x42, value.Size, ref value, 0) && (value.Flags & 1) != 0; } }
    internal static bool FontSmoothing => SystemParametersInfoBool(0x4A, 0, out var value, 0) && value != 0;
    internal static void Message(string text) => MessageBoxW(IntPtr.Zero, text, "Mail Secretary", 0);
}

internal sealed class NativeTray : IDisposable
{
    const uint CallbackMessage = 0x8000 + 73;
    readonly IntPtr window, icon;
    readonly SubclassProc callback;
    readonly uint taskbarCreated;
    bool visible, disposed;
    string text;
    internal sealed class Command
    {
        internal string Text;
        internal readonly Action Invoke;
        internal Command(string text, Action action) { Text = text; Invoke = action; }
    }
    internal readonly List<Command> Commands = new();
    internal event EventHandler? DoubleClick, BalloonTipClicked;
    internal string Text { get => text; set { text = value; if (visible) Send(1); } }
    internal bool Visible
    {
        get => visible;
        set
        {
            if (value == visible) return;
            if (!Send(value ? 0u : 2u) && value) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not add the envelope to the Windows notification area.");
            visible = value;
        }
    }
    internal NativeTray(IntPtr window, string iconPath, string text)
    {
        this.window = window; this.text = text;
        icon = LoadImageW(IntPtr.Zero, iconPath, 1, 0, 0, 0x10 | 0x40);
        if (icon == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not load the envelope icon.");
        callback = WindowMessage;
        taskbarCreated = RegisterWindowMessageW("TaskbarCreated");
        if (!SetWindowSubclass(window, callback, 73, 0)) { DestroyIcon(icon); throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not register notification callbacks."); }
        try { Visible = true; }
        catch { RemoveWindowSubclass(window, callback, 73); DestroyIcon(icon); throw; }
    }
    Notification Data() => new() { Size = (uint)Marshal.SizeOf<Notification>(), Window = window, Id = 1,
        Flags = 1 | 2 | 4 | 0x80, Callback = CallbackMessage, Icon = icon, Tip = text[..Math.Min(text.Length, 127)], Info = "", Title = "" };
    bool Send(uint operation)
    {
        var data = Data();
        if (!Shell_NotifyIconW(operation, ref data)) return false;
        if (operation == 0)
        {
            data.Timeout = 4; // NOTIFYICON_VERSION_4; set again after Explorer recreates the taskbar.
            if (!Shell_NotifyIconW(4, ref data)) { Shell_NotifyIconW(2, ref data); return false; }
        }
        return true;
    }
    internal void ShowBalloonTip(int timeout, string title, string message)
    {
        var data = Data(); data.Flags |= 0x10; data.Timeout = (uint)timeout;
        data.Title = title[..Math.Min(title.Length, 63)]; data.Info = message[..Math.Min(message.Length, 255)]; data.InfoFlags = 1;
        if (!Shell_NotifyIconW(1, ref data)) throw new Win32Exception(Marshal.GetLastWin32Error(), "Windows did not accept the mail notification.");
    }
    IntPtr WindowMessage(IntPtr hwnd, uint message, UIntPtr wParam, IntPtr lParam, UIntPtr id, UIntPtr reference)
    {
        if (message == taskbarCreated && visible) Send(0);
        if (message == CallbackMessage)
        {
            var action = (uint)lParam.ToInt64() & 0xffff;
            if (action == 0x203 || action == 0x401) DoubleClick?.Invoke(this, EventArgs.Empty);
            else if (action == 0x405) BalloonTipClicked?.Invoke(this, EventArgs.Empty);
            else if (action == 0x205 || action == 0x7B) ShowMenu();
            return IntPtr.Zero;
        }
        return DefSubclassProc(hwnd, message, wParam, lParam);
    }
    IntPtr CreateMenu()
    {
        var menu = CreatePopupMenu();
        if (menu == IntPtr.Zero) throw new Win32Exception();
        for (int index = 0; index < Commands.Count; index++)
            if (!AppendMenuW(menu, 0, (UIntPtr)(index + 1), Commands[index].Text))
            { DestroyMenu(menu); throw new Win32Exception(); }
        return menu;
    }
    void ShowMenu()
    {
        var menu = CreateMenu();
        try
        {
            GetCursorPos(out var point); SetForegroundWindow(window);
            var selected = TrackPopupMenuEx(menu, 0x100 | 0x80 | 0x2, point.X, point.Y, window, IntPtr.Zero);
            PostMessageW(window, 0, UIntPtr.Zero, IntPtr.Zero);
            if (selected > 0 && selected <= Commands.Count) Commands[(int)selected - 1].Invoke();
        }
        finally { DestroyMenu(menu); Send(3); }
    }
    internal bool VerifyNativeState()
    {
        var menu = CreateMenu();
        try { return visible && IsWindow(window) && Send(1) && GetMenuItemCount(menu) == Commands.Count && Commands.Count == 3; }
        finally { DestroyMenu(menu); }
    }
    public void Dispose()
    {
        if (disposed) return;
        if (visible) Send(2);
        visible = false; disposed = true;
        RemoveWindowSubclass(window, callback, 73); DestroyIcon(icon);
        GC.KeepAlive(callback);
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct Notification
    {
        public uint Size; public IntPtr Window; public uint Id, Flags, Callback; public IntPtr Icon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Tip;
        public uint State, StateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Info;
        public uint Timeout;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string Title;
        public uint InfoFlags; public Guid Guid; public IntPtr BalloonIcon;
    }
    [StructLayout(LayoutKind.Sequential)] struct Point { public int X, Y; }
    delegate IntPtr SubclassProc(IntPtr window, uint message, UIntPtr wParam, IntPtr lParam, UIntPtr id, UIntPtr reference);
    [DllImport("comctl32.dll", SetLastError = true)] static extern bool SetWindowSubclass(IntPtr window, SubclassProc callback, UIntPtr id, UIntPtr reference);
    [DllImport("comctl32.dll")] static extern bool RemoveWindowSubclass(IntPtr window, SubclassProc callback, UIntPtr id);
    [DllImport("comctl32.dll")] static extern IntPtr DefSubclassProc(IntPtr window, uint message, UIntPtr wParam, IntPtr lParam);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern bool Shell_NotifyIconW(uint operation, ref Notification data);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern IntPtr LoadImageW(IntPtr instance, string path, uint type, int width, int height, uint flags);
    [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern uint RegisterWindowMessageW(string name);
    [DllImport("user32.dll")] static extern IntPtr CreatePopupMenu();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool AppendMenuW(IntPtr menu, uint flags, UIntPtr id, string text);
    [DllImport("user32.dll")] static extern uint TrackPopupMenuEx(IntPtr menu, uint flags, int x, int y, IntPtr window, IntPtr parameters);
    [DllImport("user32.dll")] static extern bool DestroyMenu(IntPtr menu);
    [DllImport("user32.dll")] static extern int GetMenuItemCount(IntPtr menu);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr window);
    [DllImport("user32.dll")] static extern bool PostMessageW(IntPtr window, uint message, UIntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr window);
}
