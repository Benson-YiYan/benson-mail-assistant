using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace BensonMail;

sealed partial class MainWindow
{
    // Exercise Windows pointer routing, rather than calling a navigation handler
    // directly: ItemClick supplies a container's Content for explicit ListViewItems.
    async Task ReportTreePointerSelfTest(Action<bool, string> check, Report expected)
    {
        navigation.SelectedIndex = 0;
        ShowPage(0);
        Restore();
        var window = WinRT.Interop.WindowNative.GetWindowHandle(this);
        ReportTreePointer.SetForegroundWindow(window);
        await Task.Delay(100);
        layout.UpdateLayout();

        async Task Click(FrameworkElement target, double? localX = null)
        {
            var visibleDeadline = DateTime.UtcNow.AddSeconds(4);
            while ((!target.IsLoaded || target.ActualWidth <= 0 || target.ActualHeight <= 0) &&
                DateTime.UtcNow < visibleDeadline) {
                layout.UpdateLayout();
                await Task.Delay(25);
            }
            layout.UpdateLayout();
            if (!target.IsLoaded || target.ActualWidth <= 0 || target.ActualHeight <= 0)
                throw new InvalidOperationException("Report tree pointer target is not visible: " + target.GetType().Name);
            var point = target.TransformToVisual((UIElement)Content).TransformPoint(new Windows.Foundation.Point(
                localX ?? target.ActualWidth / 2, target.ActualHeight / 2));
            var origin = new ReportTreePointer.Point();
            if (!ReportTreePointer.ClientToScreen(window, ref origin))
                throw new InvalidOperationException("Could not locate the report tree client area.");
            var scale = layout.XamlRoot.RasterizationScale;
            var x = origin.X + (int)Math.Round(point.X * scale);
            var y = origin.Y + (int)Math.Round(point.Y * scale);
            if (!ReportTreePointer.SetCursorPos(x, y))
                throw new InvalidOperationException("Could not position the report tree test pointer.");
            await Task.Delay(30);
            ReportTreePointer.Click();
            await Task.Delay(30);
        }
        async Task Until(Func<bool> ready, string label)
        {
            var deadline = DateTime.UtcNow.AddSeconds(4);
            while (!ready() && DateTime.UtcNow < deadline) await Task.Delay(25);
            check(ready(), label);
        }
        ListViewItem Row() => (ListViewItem)reports.Items[0];
        async Task Enter(int level, string hit)
        {
            layout.UpdateLayout();
            var row = Row();
            check(row.Tag is ReportFolder, "Report tree pointer target is a folder at level " + level);
            var contents = (StackPanel)row.Content;
            if (hit == "icon") await Click((FrameworkElement)contents.Children[0]);
            else if (hit == "text") await Click((FrameworkElement)contents.Children[1]);
            else await Click(row, row.ActualWidth - 8);
            await Until(() => reportTreePath.Count == level + 1 && reports.Items.Count == 1,
                "Real pointer click on folder " + hit + " enters report tree level " + level);
        }
        async Task SelectLeaf()
        {
            check(Row().Tag is Report leaf && leaf.path == expected.path,
                "Report tree leaf preserves original report selection and path");
            await Click(Row());
            await Until(() => SelectedReport?.path == expected.path &&
                preview.Text.Contains("建议回复") && preview.Text.Contains("附件实际内容"),
                "Real pointer click on report leaf loads the full report body");
        }

        reportTreePath.Clear(); RenderReportRows();
        check(reports.Items.Count == 1 && Row().Tag is ReportFolder,
            "Report tree begins with mailbox folders");
        await Enter(0, "icon");
        await Enter(1, "text");
        await Enter(2, "blank row space");
        await SelectLeaf();
        for (var level = 2; level >= 0; level--) {
            await Click(reportTreeUp);
            var expectedLevel = level;
            await Until(() => reportTreePath.Count == expectedLevel && reports.Items.Count == 1,
                "Real pointer click on Up returns to report tree level " + level);
        }
        await Enter(0, "blank row space");
        await Enter(1, "icon");
        await Enter(2, "text");
        await SelectLeaf();
    }

    static class ReportTreePointer
    {
        [StructLayout(LayoutKind.Sequential)] internal struct Point { public int X, Y; }
        [StructLayout(LayoutKind.Sequential)] struct MouseInput
        {
            public int X, Y;
            public uint Data, Flags, Time;
            public UIntPtr Extra;
        }
        [StructLayout(LayoutKind.Explicit)] struct InputUnion
        {
            [FieldOffset(0)] public MouseInput Mouse;
        }
        [StructLayout(LayoutKind.Sequential)] struct Input { public uint Type; public InputUnion Data; }
        [DllImport("user32.dll")] internal static extern bool ClientToScreen(IntPtr window, ref Point point);
        [DllImport("user32.dll")] internal static extern bool SetForegroundWindow(IntPtr window);
        [DllImport("user32.dll")] internal static extern bool SetCursorPos(int x, int y);
        [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint count, Input[] inputs, int size);
        internal static void Click()
        {
            var input = new[] {
                new Input { Data = new InputUnion { Mouse = new MouseInput { Flags = 0x0002 } } },
                new Input { Data = new InputUnion { Mouse = new MouseInput { Flags = 0x0004 } } }
            };
            if (SendInput((uint)input.Length, input, Marshal.SizeOf<Input>()) != input.Length)
                throw new InvalidOperationException("Windows rejected report tree test pointer input.");
        }
    }
}
