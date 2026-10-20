using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace BensonMail;

// Expander's shared WinUI template loads an unresolved TabView resource in the
// packaged desktop runtime. Use the same native Button/content pattern directly.
sealed class SenderPolicyDisclosure : UserControl
{
    readonly ContentControl body = new() { Visibility = Visibility.Collapsed, HorizontalContentAlignment = HorizontalAlignment.Stretch };
    readonly TextBlock title = new() { TextWrapping = TextWrapping.Wrap, FontFamily = MailTypography.Font };
    readonly TextBlock chevron = new() { Text = "⌄", FontSize = 18, VerticalAlignment = VerticalAlignment.Center };
    readonly Button button;
    bool expanded;
    internal string Header
    {
        get => title.Text;
        set { title.Text = value; AutomationProperties.SetName(button, value); }
    }
    internal UIElement DisclosureContent
    {
        get => (UIElement)body.Content;
        set => body.Content = value;
    }
    internal bool IsExpanded
    {
        get => expanded;
        set {
            expanded = value;
            body.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
            chevron.Text = value ? "⌃" : "⌄";
        }
    }
    internal SenderPolicyDisclosure()
    {
        HorizontalAlignment = HorizontalAlignment.Stretch;
        HorizontalContentAlignment = HorizontalAlignment.Stretch;
        var header = new Grid { ColumnSpacing = 12 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.Children.Add(title);
        Grid.SetColumn(chevron, 1); header.Children.Add(chevron);
        button = new Button { Content = header, HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch, Padding = new Thickness(12, 8, 12, 8),
            CornerRadius = new CornerRadius(6), Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
            BorderThickness = new Thickness(0), MinHeight = 42 };
        button.Click += (_, _) => IsExpanded = !IsExpanded;
        body.Padding = new Thickness(12, 4, 12, 12);
        var surface = new StackPanel { Spacing = 4 };
        surface.Children.Add(button); surface.Children.Add(body);
        Content = new Border { BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Gray), BorderThickness = new Thickness(.5),
            CornerRadius = new CornerRadius(6), Child = surface };
    }
}
