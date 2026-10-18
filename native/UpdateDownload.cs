using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace BensonMail;

sealed record DownloadProgress(long Bytes, long? Total);
sealed record VerifiedUpdate(UpdateRelease Release, string Path);

sealed class UpdateDownload : IDisposable
{
    internal const long MaximumBytes = 1024L * 1024 * 1024;
    readonly HttpClient client;
    readonly string cache;
    readonly SemaphoreSlim gate = new(1, 1);
    internal UpdateDownload(string directory, HttpMessageHandler? handler = null)
    {
        cache = directory;
        client = new HttpClient(handler ?? UpdateTransport.SystemHandler()) { Timeout = Timeout.InfiniteTimeSpan };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("MailSecretary/" + UpdateClient.InstalledVersion);
    }
    internal static void ValidateUrl(Uri url)
    {
        if (!url.IsAbsoluteUri || url.Scheme != Uri.UriSchemeHttps || url.UserInfo.Length != 0 || url.Fragment.Length != 0)
            throw new InvalidDataException("The update download requires an HTTPS URL without credentials or a fragment.");
    }
    internal async Task<VerifiedUpdate> Download(UpdateRelease release, IProgress<DownloadProgress>? progress, CancellationToken cancellation)
    {
        if (!await gate.WaitAsync(0, cancellation)) throw new InvalidOperationException("An update download is already running.");
        string? partial = null;
        try {
            ValidateUrl(release.Url);
            if (!System.Text.RegularExpressions.Regex.IsMatch(release.Version, @"\A\d{12}\z") ||
                !System.Text.RegularExpressions.Regex.IsMatch(release.Sha256, @"\A[a-fA-F0-9]{64}\z"))
                throw new InvalidDataException("Invalid update version or SHA256.");
            Directory.CreateDirectory(cache);
            // A unique partial file is never executable. Only a fully verified payload is promoted.
            partial = System.IO.Path.Combine(cache, Guid.NewGuid().ToString("N") + ".part");
            var destination = System.IO.Path.Combine(cache, "BensonMail-Setup-" + release.Version + "-" + release.Sha256.ToLowerInvariant() + ".exe");
            using var request = new HttpRequestMessage(HttpMethod.Get, release.Url);
            request.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true };
            using var headersTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            headersTimeout.CancelAfter(TimeSpan.FromSeconds(45));
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, headersTimeout.Token).ConfigureAwait(false);
            ValidateUrl(response.RequestMessage?.RequestUri ?? release.Url);
            response.EnsureSuccessStatusCode();
            var declared = response.Content.Headers.ContentLength;
            if (release.Size is <= 0 or > MaximumBytes || release.Size.HasValue && declared.HasValue && release.Size != declared)
                throw new InvalidDataException("The update size does not match its manifest.");
            var total = release.Size ?? declared;
            if (total is <= 0 or > MaximumBytes) throw new InvalidDataException("The update size is empty or exceeds the 1 GB limit.");
            await using var source = await response.Content.ReadAsStreamAsync(cancellation).ConfigureAwait(false);
            long received = 0;
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            await using (var output = new FileStream(partial, FileMode.CreateNew, FileAccess.Write, FileShare.None, 131072, true)) {
                var buffer = new byte[131072];
                while (true) {
                    using var idleTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                    idleTimeout.CancelAfter(TimeSpan.FromSeconds(45));
                    var count = await source.ReadAsync(buffer.AsMemory(), idleTimeout.Token).ConfigureAwait(false);
                    if (count == 0) break;
                    received += count;
                    if (received > MaximumBytes || total.HasValue && received > total.Value)
                        throw new InvalidDataException("The update exceeds its declared or allowed size.");
                    hash.AppendData(buffer, 0, count);
                    await output.WriteAsync(buffer.AsMemory(0, count), cancellation).ConfigureAwait(false);
                    progress?.Report(new(received, total));
                }
                await output.FlushAsync(cancellation).ConfigureAwait(false);
            }
            cancellation.ThrowIfCancellationRequested();
            if (received == 0 || total.HasValue && received != total.Value) throw new InvalidDataException("The update download is incomplete.");
            var actual = Convert.ToHexString(hash.GetHashAndReset());
            if (!string.Equals(actual, release.Sha256, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("SHA256 verification failed. The downloaded installer was discarded.");
            File.Move(partial, destination, true); partial = null;
            return new(release, destination);
        }
        catch (OperationCanceledException error) when (!cancellation.IsCancellationRequested) {
            throw new TimeoutException("The update server did not respond for 45 seconds. Please retry.", error);
        }
        finally {
            if (partial != null) { try { File.Delete(partial); } catch (IOException) { } }
            gate.Release();
        }
    }
    internal static async Task VerifyBeforeInstall(VerifiedUpdate update, CancellationToken cancellation = default)
    {
        ValidateUrl(update.Release.Url);
        await using var file = new FileStream(update.Path, FileMode.Open, FileAccess.Read, FileShare.Read, 131072, true);
        if (file.Length is <= 0 or > MaximumBytes) throw new InvalidDataException("Invalid installer size.");
        var hash = Convert.ToHexString(await SHA256.HashDataAsync(file, cancellation).ConfigureAwait(false));
        if (!string.Equals(hash, update.Release.Sha256, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("The verified installer changed. Please download it again.");
    }
    public void Dispose() => client.Dispose();

    internal sealed class FixtureHandler : HttpMessageHandler
    {
        readonly Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> fixture;
        internal FixtureHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> fixture) { this.fixture = fixture; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) => fixture(request, token);
    }
    sealed class InlineProgress : IProgress<DownloadProgress>
    {
        readonly Action<DownloadProgress> action;
        internal InlineProgress(Action<DownloadProgress> action) { this.action = action; }
        public void Report(DownloadProgress value) => action(value);
    }
    internal static async Task<string[]> OfflineTests(string folder)
    {
        var checks = new List<string>();
        void Check(bool condition, string label) { if (!condition) throw new InvalidOperationException(label); checks.Add(label); }
        var bytes = System.Text.Encoding.UTF8.GetBytes("Synthetic installer fixture; never executed.");
        var sha = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var release = new UpdateRelease("209910180900", new Uri("https://download.example.invalid/update.exe"), sha, "Fixture", bytes.Length);
        var cache = Path.Combine(folder, "update-downloads");
        HttpResponseMessage Response(HttpRequestMessage request) => new(HttpStatusCode.OK) { RequestMessage = request, Content = new ByteArrayContent(bytes) };
        using var download = new UpdateDownload(cache, new FixtureHandler((r, _) => Task.FromResult(Response(r))));
        var completed = await download.Download(release, null, default);
        await VerifyBeforeInstall(completed);
        Check(File.ReadAllBytes(completed.Path).Length == bytes.Length && completed.Release == release, "In-app stream download atomically promotes only SHA256-verified installer bound to its manifest");
        File.AppendAllText(completed.Path, "tampered");
        try { await VerifyBeforeInstall(completed); throw new Exception("Tampered installer accepted"); } catch (InvalidDataException) { }
        Check(true, "Installer is reverified immediately before launch; changed packages are rejected");
        try { await download.Download(release with { Sha256 = new string('0', 64) }, null, default); throw new Exception("Bad hash accepted"); } catch (InvalidDataException) { }
        Check(Directory.GetFiles(cache, "*.part").Length == 0, "Wrong SHA256 discards partial update without publishing an installer");
        using var failed = new UpdateDownload(cache, new FixtureHandler((r, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.BadGateway) { RequestMessage = r })));
        try { await failed.Download(release, null, default); throw new Exception("Bad HTTP accepted"); } catch (HttpRequestException) { }
        using var unsafeDownload = new UpdateDownload(cache, new FixtureHandler((r, _) => { var result = Response(r); result.RequestMessage = new(HttpMethod.Get, "http://unsafe.invalid/a.exe"); return Task.FromResult(result); }));
        try { await unsafeDownload.Download(release, null, default); throw new Exception("Unsafe redirect accepted"); } catch (InvalidDataException) { }
        Check(Directory.GetFiles(cache, "*.part").Length == 0, "HTTP errors and non-HTTPS final redirects never leave executable update data");
        using var cancel = new CancellationTokenSource();
        using var waiting = new UpdateDownload(cache, new FixtureHandler(async (r, token) => { cancel.Cancel(); await Task.Delay(1000, token); return Response(r); }));
        try { await waiting.Download(release, null, cancel.Token); throw new Exception("Cancellation ignored"); } catch (OperationCanceledException) { }
        Check(Directory.GetFiles(cache, "*.part").Length == 0, "Cancelled update removes partial files and does not execute anything");
        using var bodyCancel = new CancellationTokenSource();
        long partialBytes = 0;
        try {
            await download.Download(release, new InlineProgress(value => { partialBytes = value.Bytes; bodyCancel.Cancel(); }), bodyCancel.Token);
            throw new Exception("Streaming cancellation ignored");
        } catch (OperationCanceledException) { }
        Check(partialBytes > 0 && Directory.GetFiles(cache, "*.part").Length == 0,
            "Cancellation after body bytes have been written removes the incomplete partial installer");
        try { await download.Download(release with { Size = bytes.Length + 1 }, null, default); throw new Exception("Wrong declared size accepted"); } catch (InvalidDataException) { }
        Check(Directory.GetFiles(cache, "*.part").Length == 0, "Manifest package length is checked against headers and streamed bytes");
        var retry = await download.Download(release, null, default);
        Check(File.Exists(retry.Path), "A failed or cancelled download can be retried successfully");
        return checks.ToArray();
    }
}
