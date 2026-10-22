using System;
using System.IO;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace BensonMail;

// A finite-width WinUI track avoids ProgressBar template animation failures inside ContentDialog.
sealed class UpdateProgress : Grid
{
    readonly Border fill = new() { CornerRadius = new CornerRadius(3), HorizontalAlignment = HorizontalAlignment.Left,
        Background = new SolidColorBrush(Microsoft.UI.Colors.RoyalBlue), Width = 0 };
    double current;
    internal double Value { get => current; set { current = Math.Clamp(value, 0, 100); fill.Width = current * (double.IsNaN(Width) ? 420 : Width) / 100; } }
    internal bool IsIndeterminate { get; set; }
    internal UpdateProgress()
    {
        Width = 420; MaxWidth = 420; Height = 6;
        Children.Add(new Border { CornerRadius = new CornerRadius(3), Background = new SolidColorBrush(Windows.UI.Color.FromArgb(40, 128, 128, 128)) });
        Children.Add(fill);
    }
}

// This is shared by the real dialog and packaged UI tests. Tests supply only synthetic HTTP data.
sealed class UpdateDownloadView : IDisposable
{
    internal readonly StackPanel Content = new() { Spacing = 12, Width = 440, MaxWidth = 440 };
    internal readonly UpdateProgress Bar = new();
    internal readonly TextBlock Status = new() { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
    internal readonly Button DownloadButton = new() { Content = L.T("下载更新") };
    internal readonly Button CancelButton = new() { Content = L.T("取消下载"), Visibility = Visibility.Collapsed };
    internal readonly Button InstallButton = new() { Content = L.T("安装更新"), Visibility = Visibility.Collapsed };
    internal Func<Task<bool>>? ConfirmInstall;
    readonly UpdateRelease release;
    readonly UpdateDownload download;
    readonly Func<VerifiedUpdate, CancellationToken, Task> install;
    CancellationTokenSource? cancellation;
    internal event Action? Changed;
    internal Task? ActiveTask { get; private set; }
    internal bool Busy => ActiveTask is { IsCompleted: false };
    internal VerifiedUpdate? Verified { get; private set; }
    internal UpdateDownloadView(UpdateRelease release, UpdateDownload download, Func<VerifiedUpdate, CancellationToken, Task> install)
    {
        this.release = release; this.download = download; this.install = install;
        Content.Children.Add(new TextBlock { Text = release.Notes.Length > 0 ? release.Notes : L.T("此版本没有提供更新说明。"), TextWrapping = TextWrapping.Wrap, MaxHeight = 180, IsTextSelectionEnabled = true });
        Content.Children.Add(Bar); Content.Children.Add(Status);
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12 };
        actions.Children.Add(DownloadButton); actions.Children.Add(CancelButton); actions.Children.Add(InstallButton);
        Content.Children.Add(actions);
        DownloadButton.Click += (_, _) => BeginDownload();
        CancelButton.Click += (_, _) => Cancel();
        InstallButton.Click += async (_, _) => {
            if (ConfirmInstall == null || await ConfirmInstall()) await Install();
        };
    }
    internal void BeginDownload()
    {
        if (Busy) return;
        cancellation?.Dispose(); cancellation = new();
        ActiveTask = Run(cancellation.Token); Changed?.Invoke();
        _ = ActiveTask.ContinueWith(_ => Content.DispatcherQueue.TryEnqueue(() => Changed?.Invoke()), TaskScheduler.Default);
    }
    async Task Run(CancellationToken token)
    {
        Verified = null; InstallButton.Visibility = Visibility.Collapsed;
        DownloadButton.IsEnabled = false; CancelButton.Visibility = Visibility.Visible;
        Bar.Value = 0; Bar.IsIndeterminate = !release.Size.HasValue;
        Status.Text = L.T("正在连接更新服务器…");
        var reportProgress = true;
        try {
            var progress = new Progress<DownloadProgress>(value => {
                if (!reportProgress || token.IsCancellationRequested) return;
                if (value.Probing) {
                    Bar.IsIndeterminate = true;
                    Status.Text = L.T("正在比较下载线路…"); Changed?.Invoke();
                    return;
                }
                Bar.IsIndeterminate = !value.Total.HasValue;
                if (value.Total is > 0) Bar.Value = value.Bytes * 100.0 / value.Total.Value;
                var amount = (value.Bytes / 1048576.0).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);
                var total = value.Total.HasValue ? " / " + (value.Total.Value / 1048576.0).ToString("F1", System.Globalization.CultureInfo.InvariantCulture) : "";
                Status.Text = (value.SourceHost == null ? "" : L.T("下载线路：") + value.SourceHost + "\n") +
                    L.T("已下载：") + amount + total + " MB"; Changed?.Invoke();
            });
            Verified = await download.Download(release, progress, token);
            reportProgress = false;
            Bar.IsIndeterminate = false; Bar.Value = 100;
            Status.Text = L.T("下载完成，SHA256 校验通过。确认后将退出当前程序并打开安装程序。");
            InstallButton.Visibility = Visibility.Visible;
            DownloadButton.Visibility = Visibility.Collapsed;
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { Status.Text = L.T("下载已取消。可以重试。"); }
        catch (Exception error) { Status.Text = L.T("下载更新失败：") + UpdateTransport.ErrorDetails(error, L.Code, true); }
        finally {
            reportProgress = false;
            CancelButton.Visibility = Visibility.Collapsed;
            Bar.IsIndeterminate = false;
            DownloadButton.Content = L.T("重试下载"); DownloadButton.IsEnabled = true; Changed?.Invoke();
        }
        if (Verified != null && ConfirmInstall != null && await ConfirmInstall()) await Install(true);
    }
    internal async Task Install(bool downloadCompleted = false)
    {
        if (Verified == null || (Busy && !downloadCompleted) || !InstallButton.IsEnabled) return;
        if (cancellation == null || cancellation.IsCancellationRequested) {
            cancellation?.Dispose(); cancellation = new();
        }
        InstallButton.IsEnabled = false;
        CancelButton.Content = L.T("取消等待"); CancelButton.Visibility = Visibility.Visible;
        Status.Text = L.T("正在确认当前邮件任务已完成…");
        try {
            var token = cancellation?.Token ?? CancellationToken.None;
            await UpdateDownload.VerifyBeforeInstall(Verified, token); await install(Verified, token);
        }
        catch (OperationCanceledException) { Status.Text = L.T("已取消安装等待，可以继续使用邮件小秘书。"); }
        catch (Exception error) {
            Status.Text = L.T("无法安装更新：") + (error is InvalidOperationException ? L.T(error.Message) : UpdateTransport.ErrorDetails(error, L.Code, true));
            if (error is InvalidDataException) {
                InstallButton.Visibility = Visibility.Collapsed; Verified = null;
                DownloadButton.Visibility = Visibility.Visible;
            }
        }
        finally { InstallButton.IsEnabled = true; CancelButton.Visibility = Visibility.Collapsed; CancelButton.Content = L.T("取消下载"); Changed?.Invoke(); }
    }
    internal static async Task<string[]> OfflineUITests(XamlRoot root, string folder)
    {
        var checks = new List<string>();
        void Check(bool value, string label) { if (!value) throw new InvalidOperationException(label); checks.Add(label); }
        var bytes = System.Text.Encoding.UTF8.GetBytes("Synthetic UI fixture, not an executable");
        var sha = Convert.ToHexString(SHA256.HashData(bytes));
        var release = new UpdateRelease("209910180901", new Uri("https://download.example.invalid/ui.exe"), sha, "Synthetic in-app update", bytes.Length);
        var requests = 0; var launches = 0;
        var handler = new UpdateDownload.FixtureHandler(async (request, token) => {
            requests++; await Task.Delay(350, token);
            return new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = new ByteArrayContent(bytes) };
        });
        Program.Trace("Update fixture constructing controls");
        using var view = new UpdateDownloadView(release, new UpdateDownload(Path.Combine(folder, "update-ui-cache"), handler), (verified, _) => { launches++; return Task.CompletedTask; });
        var dialog = new ContentDialog { XamlRoot = root, Title = "Synthetic in-app update test", Content = view.Content, CloseButtonText = L.T("稍后") };
        Program.Trace("Update fixture showing dialog");
        var showing = dialog.ShowAsync();
        await Task.Delay(100);
        try {
            Program.Trace("Update fixture starting cancellation case");
            view.BeginDownload(); view.BeginDownload();
            Check(view.Busy && !view.DownloadButton.IsEnabled && view.CancelButton.Visibility == Visibility.Visible && view.InstallButton.Visibility == Visibility.Collapsed,
                "Native download UI stays responsive and disables duplicate downloads; installation is hidden before SHA256 verification");
            await Task.Delay(30); view.Cancel(); await view.ActiveTask!;
            Check(view.Verified == null && launches == 0 && view.DownloadButton.IsEnabled,
                "Native Cancel restores Retry without launching any file");
            Program.Trace("Update fixture starting success case");
            view.BeginDownload();
            dialog.Hide(); await showing;
            Check(view.Busy && launches == 0, "Later dismisses the download dialog without cancelling its active background task or launching the installer");
            await view.ActiveTask!;
            Check(view.Verified != null && view.Bar.Value == 100 && view.InstallButton.Visibility == Visibility.Visible && launches == 0 && requests == 2,
                "Native retry finishes with verified-install action; download completion never executes installer");
            var info = UpdateInstall.StartInfo(view.Verified!, @"C:\Users\Fixture User\BensonMail", "en", 12345);
            Check(!info.UseShellExecute && info.CreateNoWindow && info.FileName == view.Verified!.Path &&
                info.ArgumentList.Contains(@"/DIR=C:\Users\Fixture User\BensonMail") && info.ArgumentList.Contains("/UPDATEPID=12345") && info.ArgumentList.Contains("/LANG=english"),
                "Install handoff directly starts the verified native Setup with original directory, language and wait-for-parent arguments; no cmd");
            Program.Trace("Update fixture explicit install action");
            await view.Install();
            Check(launches == 1, "Only explicit Install action invokes an injected installer callback; test never executes fixture payloads");
            using var rejected = new UpdateDownloadView(release, new UpdateDownload(Path.Combine(folder, "update-rejected-cache"),
                new UpdateDownload.FixtureHandler((request, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = new ByteArrayContent(bytes) }))),
                (_, _) => throw new InvalidOperationException("Setup rejected the target directory; see installation log."));
            rejected.BeginDownload(); await rejected.ActiveTask!; await rejected.Install();
            Check(rejected.Status.Text.Contains("Setup rejected the target directory") && rejected.InstallButton.IsEnabled,
                "Installer handoff rejection is actionable in native UI, restores Install and does not report success");
            foreach (var accepted in new[] { false, true }) {
                var prompts = 0; var automaticLaunches = 0;
                using var prompted = new UpdateDownloadView(release, new UpdateDownload(Path.Combine(folder, "update-prompt-" + accepted),
                    new UpdateDownload.FixtureHandler((request, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = new ByteArrayContent(bytes) }))),
                    (_, _) => { automaticLaunches++; return Task.CompletedTask; });
                prompted.ConfirmInstall = () => { prompts++; return Task.FromResult(accepted); };
                prompted.BeginDownload(); await prompted.ActiveTask!;
                Check(prompts == 1 && automaticLaunches == (accepted ? 1 : 0) && prompted.Verified != null,
                    accepted ? "Verified download prompts once and installs immediately after confirmation" : "Later retains the verified package without installing");
            }
            File.AppendAllText(view.Verified!.Path, "changed");
            Program.Trace("Update fixture explicit install action");
            await view.Install();
            Check(launches == 1 && view.Verified == null && view.InstallButton.Visibility == Visibility.Collapsed,
                "Package changed after download is rejected by native install action before launch");
        }
        finally { Program.Trace("Update fixture hiding dialog"); view.Cancel(); if (view.ActiveTask != null) await view.ActiveTask; dialog.Hide(); await showing; }
        return checks.ToArray();
    }
    internal void Cancel() { cancellation?.Cancel(); if (Verified != null && !InstallButton.IsEnabled) Status.Text = L.T("正在取消安装等待…"); }
    public void Dispose() { cancellation?.Dispose(); download.Dispose(); }
}
