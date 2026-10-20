using System;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;

namespace BensonMail;

// The packaged WinUI ProgressRing template loads an unresolved shared resource on
// supported runner builds. Draw this small native indicator directly so it does
// not depend on that template or load unrelated control-resource dictionaries.
sealed class ConversationBusyIndicator : UserControl
{
    readonly RotateTransform rotation = new();
    readonly DispatcherQueueTimer timer;
    bool active;
    internal bool IsActive
    {
        get => active;
        set {
            active = value;
            Visibility = value ? Visibility.Visible : Visibility.Collapsed;
            if (value && IsLoaded) timer.Start(); else timer.Stop();
        }
    }
    internal ConversationBusyIndicator()
    {
        Width = Height = 20;
        IsHitTestVisible = false;
        Visibility = Visibility.Collapsed;
        var drawing = new Grid { Width = 20, Height = 20, RenderTransform = rotation, RenderTransformOrigin = new Point(.5, .5) };
        drawing.Children.Add(new Ellipse { Width = 16, Height = 16, StrokeThickness = 2,
            Stroke = new SolidColorBrush(Microsoft.UI.Colors.Gray), Opacity = .35 });
        drawing.Children.Add(new Ellipse { Width = 4, Height = 4, VerticalAlignment = VerticalAlignment.Top,
            HorizontalAlignment = HorizontalAlignment.Center, Fill = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 0, 120, 212)) });
        Content = drawing;
        timer = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        timer.Interval = TimeSpan.FromMilliseconds(80);
        timer.Tick += (_, _) => rotation.Angle = (rotation.Angle + 30) % 360;
        Loaded += (_, _) => { if (active) timer.Start(); };
        Unloaded += (_, _) => timer.Stop();
    }
}
