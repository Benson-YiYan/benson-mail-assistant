using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace BensonMail;

static class UpdateInstall
{
    internal static string Cache => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "BensonMail", "update-cache");
    internal static ProcessStartInfo StartInfo(VerifiedUpdate update, string installDirectory, string language, int pid,
        string? statusPath = null, string? logPath = null)
    {
        if (!Regex.IsMatch(update.Release.Version, @"\A\d{12}\z")) throw new InvalidDataException("Invalid update version.");
        if (!Path.IsPathFullyQualified(update.Path) || Path.GetExtension(update.Path) != ".exe") throw new InvalidDataException("Invalid installer path.");
        var start = new ProcessStartInfo(update.Path) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(update.Path)! };
        start.ArgumentList.Add("/UPDATE=1");
        start.ArgumentList.Add("/UPDATEPID=" + pid);
        start.ArgumentList.Add("/DIR=" + Path.TrimEndingDirectorySeparator(installDirectory));
        start.ArgumentList.Add("/LANG=" + (language == "zh" ? "chinesesimp" : "english"));
        start.ArgumentList.Add("/NORESTART");
        start.ArgumentList.Add("/SILENT"); // Native progress UI and actionable installer errors; no unattended wizard pages.
        start.ArgumentList.Add("/SP-");
        if (statusPath != null) start.ArgumentList.Add("/UPDATESTATUS=" + statusPath);
        if (logPath != null) start.ArgumentList.Add("/LOG=" + logPath);
        return start;
    }
    internal static async Task<Process> Start(VerifiedUpdate update, string installDirectory, string language, int pid,
        CancellationToken cancellation, bool fixture = false)
    {
        await UpdateDownload.VerifyBeforeInstall(update, cancellation);
        var directory = Path.GetDirectoryName(update.Path)!;
        Directory.CreateDirectory(directory);
        var stem = "install-" + update.Release.Version + "-" + Guid.NewGuid().ToString("N");
        var status = Path.Combine(directory, stem + ".status");
        var log = Path.Combine(directory, stem + ".log");
        File.WriteAllText(Path.Combine(directory, "last-install-attempt.json"), JsonSerializer.Serialize(new { version = update.Release.Version, status, log }));
        var info = StartInfo(update, installDirectory, language, pid, status, log);
        if (fixture) { info.ArgumentList.Add("/UPDATENORELAUNCH=1"); info.ArgumentList.Add("/SUPPRESSMSGBOXES"); }
        var process = Process.Start(info) ?? throw new IOException(L.T("安装程序未能启动，请重试。"));
        try {
            var deadline = DateTime.UtcNow.AddSeconds(20);
            while (DateTime.UtcNow < deadline) {
                cancellation.ThrowIfCancellationRequested();
                if (File.Exists(status)) {
                    string response;
                    try { response = File.ReadAllText(status).Trim(); }
                    catch (IOException) { await Task.Delay(100, cancellation); continue; }
                    if (response.Replace("\r\n", "\n") == "ready\n" + update.Release.Version) return process;
                    if (response.StartsWith("failed", StringComparison.Ordinal)) throw new InvalidOperationException(response + "\n" + L.T("安装日志：") + log);
                }
                if (process.HasExited) throw new InvalidOperationException(L.T("安装程序提前退出，尚未开始更新。退出代码：") + process.ExitCode + "\n" + L.T("安装日志：") + log);
                await Task.Delay(100, cancellation);
            }
            throw new TimeoutException(L.T("安装程序在20秒内未确认启动，当前应用将继续运行。请检查系统安全提示后重试。") + "\n" + L.T("安装日志：") + log);
        }
        catch { process.Dispose(); throw; }
    }
    internal static string PreviousOutcome()
    {
        try {
            using var state = JsonDocument.Parse(File.ReadAllText(Path.Combine(Cache, "last-install-attempt.json")));
            var version = state.RootElement.GetProperty("version").GetString()!;
            var status = state.RootElement.GetProperty("status").GetString()!;
            var log = state.RootElement.GetProperty("log").GetString()!;
            if (!Regex.IsMatch(version, @"\A\d{12}\z") || Path.GetDirectoryName(Path.GetFullPath(status)) != Cache || Path.GetDirectoryName(Path.GetFullPath(log)) != Cache) return "";
            var result = File.Exists(status) ? File.ReadAllText(status).Trim() : "";
            if (result.StartsWith("installed") && UpdateClient.InstalledVersion == version) return L.T("更新已完成：") + version;
            return L.T("上次更新尚未确认完成。可以重试安装；详情请查看日志：") + log + (result.StartsWith("failed") ? "\n" + result : "");
        }
        catch { return ""; }
    }
    internal static bool Fixture(string[] args)
    {
        var index = Array.IndexOf(args, "--install-update-fixture");
        if (index < 0) return false;
        try {
            var root = Directory.GetParent(Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory))!.FullName;
            if (!File.Exists(Path.Combine(root, ".benson-uninstall-fixture"))) throw new InvalidOperationException("Update fixtures require a synthetic installation marker.");
            using var request = JsonDocument.Parse(File.ReadAllText(args[index + 1]));
            var data = request.RootElement;
            var release = new UpdateRelease(data.GetProperty("version").GetString()!, new Uri("https://fixture.example.invalid/update.exe"), data.GetProperty("sha256").GetString()!, "Offline installer fixture");
            var verified = new VerifiedUpdate(release, data.GetProperty("installer").GetString()!);
            using var mutex = new Mutex(false, @"Local\BensonMail-" + Environment.UserName);
            var target = data.TryGetProperty("target", out var targetValue) ? targetValue.GetString()! : AppContext.BaseDirectory;
            if (Path.GetDirectoryName(Path.TrimEndingDirectorySeparator(Path.GetFullPath(target))) != root) throw new InvalidOperationException("Fixture targets must stay inside the synthetic root.");
            using var process = Start(verified, target, "en", Environment.ProcessId, CancellationToken.None, true).GetAwaiter().GetResult();
            File.WriteAllText(data.GetProperty("result").GetString()!, JsonSerializer.Serialize(new { ok = true, parent = Environment.ProcessId, installer = process.Id }));
            Environment.ExitCode = 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); Environment.ExitCode = 2; }
        return true;
    }
}
