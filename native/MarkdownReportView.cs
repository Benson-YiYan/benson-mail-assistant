using System;
using Markdig;
using Markdig.Syntax;
using Markdig.Syntax.Inlines;
using Markdig.Extensions.Tables;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Text;

namespace BensonMail;

// Parse Markdown as data into native controls. No HTML engine, remote images or scripts.
internal sealed class MarkdownReportView : ScrollViewer
{
    static readonly MarkdownPipeline Pipeline = new MarkdownPipelineBuilder().UsePipeTables().DisableHtml().Build();
    string text = "";
    bool markdown = true;
    public string Text { get => text; set => Show(value, markdown); }
    public int HeadingCount { get; private set; }
    public int TableCount { get; private set; }
    public int LinkCount { get; private set; }
    public int CodeCount { get; private set; }
    public int ListCount { get; private set; }
    public int BoldCount { get; private set; }
    public void Show(string value, bool isMarkdown)
    {
        text = value; markdown = isMarkdown;
        HeadingCount = TableCount = LinkCount = CodeCount = ListCount = BoldCount = 0;
        var stack = new StackPanel { Spacing = 12, Padding = new Thickness(12) };
        if (isMarkdown) Blocks(Markdown.Parse(value, Pipeline), stack);
        else stack.Children.Add(Plain(value));
        Content = stack;
        HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled;
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto;
    }
    TextBlock Plain(string value) => new() { Text = value, IsTextSelectionEnabled = true,
        FontFamily = FontFamily, FontSize = FontSize, TextWrapping = TextWrapping.Wrap };
    RichTextBlock Rich(LeafBlock block, int heading = 0)
    {
        var rich = new RichTextBlock { FontFamily = FontFamily, FontSize = heading > 0 ? Math.Max(16, 29 - heading * 3) : FontSize,
            IsTextSelectionEnabled = true, TextWrapping = TextWrapping.Wrap };
        var paragraph = new Paragraph();
        if (block.Inline != null) Inlines(block.Inline, paragraph.Inlines);
        if (heading > 0) paragraph.FontWeight = FontWeights.SemiBold;
        rich.Blocks.Add(paragraph); return rich;
    }
    void Blocks(ContainerBlock source, StackPanel target)
    {
        foreach (var block in source)
        {
            if (block is HeadingBlock heading) { HeadingCount++; target.Children.Add(Rich(heading, heading.Level)); }
            else if (block is Markdig.Extensions.Tables.Table table)
            {
                TableCount++;
                var grid = new Grid { ColumnSpacing = 1, RowSpacing = 1 };
                int columns = 0;
                foreach (TableRow row in table) columns = Math.Max(columns, row.Count);
                for (int col = 0; col < columns; col++) grid.ColumnDefinitions.Add(new ColumnDefinition());
                int index = 0;
                foreach (TableRow row in table)
                {
                    grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
                    int col = 0;
                    foreach (TableCell cell in row)
                    {
                        var contents = new StackPanel { Spacing = 4 };
                        Blocks(cell, contents);
                        if (row.IsHeader)
                            foreach (var child in contents.Children)
                                if (child is RichTextBlock header) header.FontWeight = FontWeights.SemiBold;
                        var border = new Border { Padding = new Thickness(8), BorderThickness = new Thickness(.5),
                            BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Gray), Child = contents };
                        Grid.SetRow(border, index); Grid.SetColumn(border, col++); grid.Children.Add(border);
                    }
                    index++;
                }
                target.Children.Add(grid);
            }
            else if (block is ListBlock list)
            {
                ListCount++; int number = int.TryParse(list.OrderedStart, out var parsed) ? parsed : 1;
                foreach (ListItemBlock item in list)
                {
                    var line = new Grid { ColumnSpacing = 8 };
                    line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
                    line.ColumnDefinitions.Add(new ColumnDefinition());
                    line.Children.Add(Plain(list.IsOrdered ? (number++).ToString() + "." : "•"));
                    var contents = new StackPanel { Spacing = 4 }; Blocks(item, contents);
                    Grid.SetColumn(contents, 1); line.Children.Add(contents); target.Children.Add(line);
                }
            }
            else if (block is CodeBlock code)
            {
                CodeCount++;
                var view = Plain(code.Lines.ToString()); view.FontFamily = new FontFamily("Cascadia Mono, Consolas");
                target.Children.Add(new Border { Padding = new Thickness(12), CornerRadius = new CornerRadius(4),
                    Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent), BorderThickness = new Thickness(1),
                    BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Gray), Child = view });
            }
            else if (block is LeafBlock leaf) target.Children.Add(Rich(leaf));
            else if (block is ContainerBlock container)
            { var nested = new StackPanel { Spacing = 8, Margin = new Thickness(12, 0, 0, 0) }; Blocks(container, nested); target.Children.Add(nested); }
        }
    }
    void Inlines(ContainerInline source, InlineCollection destination)
    {
        foreach (var inline in source)
        {
            if (inline is LiteralInline literal) destination.Add(new Run { Text = literal.Content.ToString() });
            else if (inline is LineBreakInline) destination.Add(new LineBreak());
            else if (inline is CodeInline code) destination.Add(new Run { Text = code.Content, FontFamily = new FontFamily("Cascadia Mono, Consolas") });
            else if (inline is EmphasisInline emphasis)
            {
                Span span = emphasis.DelimiterCount >= 2 ? new Bold() : new Italic();
                if (emphasis.DelimiterCount >= 2) BoldCount++;
                Inlines(emphasis, span.Inlines); destination.Add(span);
            }
            else if (inline is LinkInline link)
            {
                if (!link.IsImage && Uri.TryCreate(link.Url, UriKind.Absolute, out var uri) &&
                    (uri.Scheme == "https" || uri.Scheme == "http" || uri.Scheme == "mailto"))
                { var hyperlink = new Hyperlink { NavigateUri = uri }; Inlines(link, hyperlink.Inlines); destination.Add(hyperlink); LinkCount++; }
                else { var span = new Span(); Inlines(link, span.Inlines); destination.Add(span); }
            }
            else if (inline is ContainerInline container) Inlines(container, destination);
            else destination.Add(new Run { Text = inline.ToString() ?? "" });
        }
    }
}
