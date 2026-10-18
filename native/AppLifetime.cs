using System;
using System.Diagnostics;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32.SafeHandles;

namespace BensonMail;

// Current-user-only IPC, scoped to the installed directory. Never terminate processes by name.
sealed class AppLifetime : IDisposable
{
    readonly string directory;
    readonly Action exit;
    readonly CancellationTokenSource cancellation = new();
    readonly Task server;
    internal AppLifetime(string directory, Action exit)
    {
        this.directory = Normalize(directory); this.exit = exit;
        server = Task.Run(Listen);
    }
    static string Normalize(string directory) => Path.TrimEndingDirectorySeparator(Path.GetFullPath(directory)).ToUpperInvariant();
    static string PipeName(string directory) => "BensonMail-Exit-" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Normalize(directory) + "|" + Environment.UserName)))[..32];
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetNamedPipeServerProcessId(SafePipeHandle pipe, out uint processId);
    async Task Listen()
    {
        while (!cancellation.IsCancellationRequested) {
            try {
                await using var pipe = new NamedPipeServerStream(PipeName(directory), PipeDirection.InOut, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await pipe.WaitForConnectionAsync(cancellation.Token);
                using var requestTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation.Token);
                requestTimeout.CancelAfter(TimeSpan.FromSeconds(5));
                using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, true);
                using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
                var line = await reader.ReadLineAsync(requestTimeout.Token);
                using var request = JsonDocument.Parse(line ?? "{}");
                if (request.RootElement.GetProperty("command").GetString() != "shutdown" ||
                    Normalize(request.RootElement.GetProperty("directory").GetString()!) != directory) continue;
                await writer.WriteLineAsync(JsonSerializer.Serialize(new { ok = true, pid = Environment.ProcessId, launcher = Environment.ProcessPath }));
                exit();
                return;
            }
            catch (OperationCanceledException) { }
            catch (Exception error) when (error is IOException || error is JsonException || error is InvalidOperationException || error is KeyNotFoundException) { }
        }
    }
    internal static Process? FindRunning(string directory)
    {
        var expected = Normalize(directory);
        foreach (var process in Process.GetProcesses()) {
            try {
                if (process.Id != Environment.ProcessId && Regex.IsMatch(process.ProcessName, @"\ABensonMail-\d{12}\z", RegexOptions.IgnoreCase) &&
                    process.MainModule?.FileName is string path && Normalize(Path.GetDirectoryName(path)!) == expected)
                    return process;
            }
            catch (Exception error) when (error is System.ComponentModel.Win32Exception || error is InvalidOperationException) { }
            process.Dispose();
        }
        return null;
    }
    internal static async Task RequestExit(string directory, Process expected)
    {
        if (expected.HasExited) return;
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(35));
        try {
            await using var pipe = new NamedPipeClientStream(".", PipeName(directory), PipeDirection.InOut, PipeOptions.Asynchronous);
            await pipe.ConnectAsync(3000, timeout.Token);
            if (!GetNamedPipeServerProcessId(pipe.SafePipeHandle, out var serverPid) || serverPid != expected.Id)
                throw new IOException(L.T("无法确认正在运行的程序身份，未执行卸载。"));
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true };
            using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, true);
            await writer.WriteLineAsync(JsonSerializer.Serialize(new { command = "shutdown", directory = Normalize(directory) }));
            var reply = await reader.ReadLineAsync(timeout.Token);
            using var response = JsonDocument.Parse(reply ?? "{}");
            if (!response.RootElement.GetProperty("ok").GetBoolean() || response.RootElement.GetProperty("pid").GetInt32() != expected.Id ||
                Normalize(Path.GetDirectoryName(response.RootElement.GetProperty("launcher").GetString()!)!) != Normalize(directory))
                throw new IOException(L.T("程序没有确认退出请求，未执行卸载。"));
            await expected.WaitForExitAsync(timeout.Token);
        }
        catch (Exception error) when (error is OperationCanceledException || error is TimeoutException) {
            throw new IOException(L.T("等待邮件小秘书退出超时。没有删除任何文件，请稍后重试。"), error);
        }
        catch (IOException error) { throw new IOException(L.T("无法自动退出邮件小秘书。没有删除任何文件；请退出程序后重试。"), error); }
    }
    internal static bool TestProcess(string[] args)
    {
        var serverIndex = Array.IndexOf(args, "--lifetime-pipe-test");
        var clientIndex = Array.IndexOf(args, "--request-app-exit-test");
        if (serverIndex < 0 && clientIndex < 0) return false;
        var root = Directory.GetParent(Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory))?.FullName;
        if (root == null || !File.Exists(Path.Combine(root, ".benson-uninstall-fixture"))) { Environment.ExitCode = 2; return true; }
        if (serverIndex >= 0 && serverIndex + 1 < args.Length) {
            using var heldMutex = new Mutex(false, @"Local\BensonMail-" + Environment.UserName);
            using var exited = new ManualResetEventSlim();
            using var lifetime = new AppLifetime(AppContext.BaseDirectory, () => exited.Set());
            File.WriteAllText(args[serverIndex + 1], "ready");
            if (!exited.Wait(TimeSpan.FromSeconds(40))) Environment.ExitCode = 3;
            return true;
        }
        if (clientIndex >= 0 && clientIndex + 1 < args.Length) {
            using var running = FindRunning(AppContext.BaseDirectory);
            if (running == null) { Environment.ExitCode = 4; return true; }
            RequestExit(AppContext.BaseDirectory, running).GetAwaiter().GetResult();
            File.WriteAllText(args[clientIndex + 1], "gracefully exited with acknowledged current-user IPC; no process killed");
            return true;
        }
        Environment.ExitCode = 2; return true;
    }
    public void Dispose() { cancellation.Cancel(); }
}
