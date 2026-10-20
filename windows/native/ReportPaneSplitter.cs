using System;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.System;

namespace BensonMail;

/// <summary>A native, keyboard-accessible row divider without an extra toolkit runtime.</summary>
sealed class ReportPaneSplitter : UserControl
{
    readonly Grid host;
    readonly int upper, lower;
    double startY, startHeight;
    uint? pointer;
    internal ReportPaneSplitter(Grid host, int upper, int lower)
    {
        this.host = host; this.upper = upper; this.lower = lower;
        Height = 14; IsTabStop = true;
        ProtectedCursor = InputSystemCursor.Create(InputSystemCursorShape.SizeNorthSouth);
        var surface = new Grid { Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent) };
        surface.Children.Add(new Border { Height = 3, Width = 56, CornerRadius = new CornerRadius(2),
            Background = new SolidColorBrush(Microsoft.UI.Colors.Gray), Opacity = .5,
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center });
        Content = surface;
        PointerPressed += (_, e) => {
            if (!e.GetCurrentPoint(this).Properties.IsLeftButtonPressed) return;
            startY = e.GetCurrentPoint(host).Position.Y; startHeight = host.RowDefinitions[upper].ActualHeight;
            if (CapturePointer(e.Pointer)) { pointer = e.Pointer.PointerId; Focus(FocusState.Pointer); e.Handled = true; }
        };
        PointerMoved += (_, e) => {
            if (pointer != e.Pointer.PointerId) return;
            ResizeUpperPane(startHeight + e.GetCurrentPoint(host).Position.Y - startY); e.Handled = true;
        };
        PointerReleased += (_, e) => {
            if (pointer != e.Pointer.PointerId) return;
            pointer = null; ReleasePointerCapture(e.Pointer); e.Handled = true;
        };
        PointerCaptureLost += (_, _) => pointer = null;
        KeyDown += (_, e) => {
            if (e.Key is not (VirtualKey.Up or VirtualKey.Down)) return;
            ResizeUpperPane(host.RowDefinitions[upper].ActualHeight + (e.Key == VirtualKey.Up ? -24 : 24)); e.Handled = true;
        };
    }
    internal void SetLabel(string value)
    {
        AutomationProperties.SetName(this, value);
        ToolTipService.SetToolTip(this, value);
    }
    internal void ResizeUpperPane(double requested)
    {
        var first = host.RowDefinitions[upper]; var second = host.RowDefinitions[lower];
        var available = first.ActualHeight + second.ActualHeight;
        if (available <= first.MinHeight + second.MinHeight) return;
        var height = Math.Clamp(requested, first.MinHeight, available - second.MinHeight);
        first.Height = new GridLength(height, GridUnitType.Star);
        second.Height = new GridLength(available - height, GridUnitType.Star);
    }
}
