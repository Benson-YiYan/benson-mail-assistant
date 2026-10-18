using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace BensonMail;

sealed record UpdateRelease(string Version, Uri Url, string Sha256, string Notes);

sealed class UpdateClient
{
    internal const string ManifestUrl = "https://raw.githubusercontent.com/Benson-YiYan/benson-mail-updates/main/manifest.json";
    static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(10), MaxResponseContentBufferSize = 512 * 1024 };
    readonly string statePath;
    readonly string current;
    readonly Func<Task<string>> fetch;
    readonly Func<DateTimeOffset> now;
    readonly SemaphoreSlim gate = new(1, 1);
    sealed class State { public State() { } public DateTimeOffset LastCheck { get; set; } public string SeenVersion { get; set; } = ""; }
    internal static string InstalledVersion
    {
        get {
            var path = Path.Combine(AppContext.BaseDirectory, "build-version.txt");
            var version = File.Exists(path) ? File.ReadAllText(path).Trim().Trim('\uFEFF') : "";
            return Regex.IsMatch(version, @"^\d{12}$") ? version : "000000000000";
        }
    }
    internal UpdateClient(string path, string version, Func<Task<string>>? fetchManifest = null, Func<DateTimeOffset>? clock = null)
    {
        statePath = path; current = version; now = clock ?? (() => DateTimeOffset.UtcNow);
        fetch = fetchManifest ?? (() => Http.GetStringAsync(ManifestUrl));
    }
    State Load()
    {
        try { return JsonSerializer.Deserialize<State>(File.ReadAllText(statePath)) ?? new(); }
        catch (Exception e) when (e is IOException || e is JsonException) { return new(); }
    }
    void Save(State state)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(statePath)!);
        var temporary = statePath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(state));
        File.Move(temporary, statePath, true);
    }
    internal static UpdateRelease Parse(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        if (!root.TryGetProperty("schema_version", out var schema) || schema.GetInt32() != 1 ||
            !root.TryGetProperty("platforms", out var platforms) || !platforms.TryGetProperty("windows-x64", out var release))
            throw new InvalidDataException("更新清单尚未准备好。");
        string Read(string key) => release.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString()! : "";
        var version = Read("version"); var sha = Read("sha256"); var notes = Read("notes");
        if (!Regex.IsMatch(version, @"^\d{12}$") || !DateTime.TryParseExact(version, "yyyyMMddHHmm", CultureInfo.InvariantCulture, DateTimeStyles.None, out _) ||
            !Regex.IsMatch(sha, @"\A[a-fA-F0-9]{64}\z") || !Uri.TryCreate(Read("url"), UriKind.Absolute, out var url) ||
            url.Scheme != Uri.UriSchemeHttps || string.IsNullOrEmpty(url.Host) || url.UserInfo.Length > 0 || url.Fragment.Length > 0)
            throw new InvalidDataException("更新清单内容无效。");
        return new(version, url, sha.ToLowerInvariant(), notes.Length <= 8000 ? notes : notes[..8000]);
    }
    internal async Task<UpdateRelease?> Check(bool manual)
    {
        if (manual) await gate.WaitAsync();
        else if (!await gate.WaitAsync(0)) return null;
        try {
            var state = Load(); var time = now(); var elapsed = time - state.LastCheck;
            if (!manual && elapsed >= TimeSpan.FromMinutes(-5) && elapsed < TimeSpan.FromHours(5)) return null;
            // Persist before the request, including failed automatic requests, to avoid retrying on every launch.
            state.LastCheck = time; Save(state);
            var release = Parse(await fetch());
            if (string.CompareOrdinal(release.Version, current) <= 0) return null;
            if (!manual && state.SeenVersion == release.Version) return null;
            state.SeenVersion = release.Version; Save(state);
            return release;
        }
        finally { gate.Release(); }
    }
    internal static async Task<string[]> OfflineTests(string folder)
    {
        var checks = new List<string>();
        void Check(bool ok, string label) { if (!ok) throw new InvalidOperationException(label); checks.Add(label); }
        string Manifest(string version, string url = "https://downloads.example.invalid/mail.exe", string? sha = null) =>
            JsonSerializer.Serialize(new { schema_version = 1, platforms = new Dictionary<string, object> {
                ["windows-x64"] = new { version, url, sha256 = sha ?? new string('a', 64), notes = "Synthetic release notes" } } });
        var time = new DateTimeOffset(2026, 10, 18, 0, 0, 0, TimeSpan.Zero); var calls = 0;
        var path = Path.Combine(folder, "updates.json");
        Task<string> Fetch() { calls++; return Task.FromResult(Manifest("209910180900")); }
        var client = new UpdateClient(path, "202610180900", Fetch, () => time);
        var release = await client.Check(false);
        Check(release?.Url.Host == "downloads.example.invalid", "HTTPS update download can use a different host from manifest");
        Check(await new UpdateClient(path, "202610180900", Fetch, () => time).Check(false) == null && calls == 1,
            "Automatic five-hour interval persists across restarts");
        Check(await client.Check(true) != null && calls == 2, "Manual update check bypasses automatic interval");
        time += TimeSpan.FromHours(5);
        Check(await client.Check(false) == null && calls == 3, "Five-hour automatic check runs but does not repeat the same release notification");
        foreach (var invalid in new[] { "{}", Manifest("209913180900"), Manifest("209910180900", "http://unsafe.invalid/a.exe"), Manifest("209910180900", sha: "bad"), Manifest("209910180900", "https://user:secret@example.invalid/a.exe") }) {
            try { Parse(invalid); throw new InvalidOperationException("Invalid update manifest accepted"); }
            catch (Exception e) when (e is InvalidDataException || e is JsonException) { }
        }
        Check(true, "Empty manifests, invalid versions, unsafe URLs and invalid SHA256 rejected offline");
        var failedPath = Path.Combine(folder, "failed-update.json");
        var failures = 0;
        Task<string> Failure() { failures++; throw new HttpRequestException("Synthetic offline failure"); }
        try { await new UpdateClient(failedPath, "202610180900", Failure, () => time).Check(true); throw new Exception("Missing network error"); }
        catch (HttpRequestException) { }
        Check(await new UpdateClient(failedPath, "202610180900", Failure, () => time).Check(false) == null && failures == 1,
            "Failed checks preserve retry interval; manual errors remain available to UI");
        Check(await new UpdateClient(Path.Combine(folder, "same-version.json"), "209910180900", Fetch).Check(true) == null,
            "Current version is never offered as an update");
        return checks.ToArray();
    }
}
