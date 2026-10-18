using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;

namespace BensonMail;

sealed record DownloadProgress(long Bytes, long? Total, string? SourceHost = null, bool Probing = false);
sealed record VerifiedUpdate(UpdateRelease Release, string Path);

sealed class UpdateDownload : IDisposable
{
    internal const long MaximumBytes = 1024L * 1024 * 1024;
    internal const int ProbeBytes = 256 * 1024;
    readonly HttpClient client;
    readonly TimeSpan probeTimeout;
    readonly string cache;
    readonly SemaphoreSlim gate = new(1, 1);
    internal UpdateDownload(string directory, HttpMessageHandler? handler = null, TimeSpan? probeLimit = null)
    {
        cache = directory;
        probeTimeout = probeLimit ?? TimeSpan.FromSeconds(8);
        client = new HttpClient(handler ?? UpdateTransport.SystemHandler()) { Timeout = Timeout.InfiniteTimeSpan };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("MailSecretary/" + UpdateClient.InstalledVersion);
    }
    internal static void ValidateUrl(Uri url)
    {
        if (!url.IsAbsoluteUri || url.Scheme != Uri.UriSchemeHttps || url.UserInfo.Length != 0 || url.Fragment.Length != 0)
            throw new InvalidDataException("The update download requires an HTTPS URL without credentials or a fragment.");
    }
    async Task<double?> Probe(Uri url, CancellationToken cancellation)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(probeTimeout);
        try {
            var watch = Stopwatch.StartNew();
            using var request = new HttpRequestMessage(HttpMethod.Get, url);
            request.Headers.Range = new RangeHeaderValue(0, ProbeBytes - 1);
            request.Headers.AcceptEncoding.ParseAdd("identity");
            request.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true };
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token).ConfigureAwait(false);
            ValidateUrl(response.RequestMessage?.RequestUri ?? url);
            response.EnsureSuccessStatusCode();
            if (response.StatusCode == HttpStatusCode.PartialContent && response.Content.Headers.ContentRange?.From != 0)
                return null;
            await using var stream = await response.Content.ReadAsStreamAsync(timeout.Token).ConfigureAwait(false);
            var buffer = new byte[32768];
            var received = 0;
            while (received < ProbeBytes) {
                var count = await stream.ReadAsync(buffer.AsMemory(0, Math.Min(buffer.Length, ProbeBytes - received)), timeout.Token).ConfigureAwait(false);
                if (count == 0) break;
                received += count;
            }
            // Range-ignoring servers are closed after at most 256 KiB too; never probe the full package.
            cancellation.ThrowIfCancellationRequested();
            return received > 0 ? received / Math.Max(watch.Elapsed.TotalSeconds, .000001) : null;
        }
        catch (OperationCanceledException) when (!cancellation.IsCancellationRequested) { return null; }
        catch (Exception error) when (error is HttpRequestException or IOException) { return null; }
    }
    async Task<List<Uri>> OrderedSources(UpdateRelease release, IProgress<DownloadProgress>? progress, CancellationToken cancellation)
    {
        var sources = new List<Uri> { release.Url };
        if (release.Mirrors != null) foreach (var mirror in release.Mirrors) {
            ValidateUrl(mirror);
            if (!sources.Contains(mirror)) sources.Add(mirror);
        }
        if (sources.Count > 4) throw new InvalidDataException("Too many update sources.");
        if (sources.Count < 2) return sources;
        progress?.Report(new(0, release.Size, null, true));
        var results = await Task.WhenAll(sources.Select(async url => (Url: url, Speed: await Probe(url, cancellation).ConfigureAwait(false)))).ConfigureAwait(false);
        cancellation.ThrowIfCancellationRequested();
        // Failed probes remain last-resort sources, including servers which reject Range requests.
        return results.OrderByDescending(result => result.Speed ?? -1).Select(result => result.Url).ToList();
    }
    internal async Task<VerifiedUpdate> Download(UpdateRelease release, IProgress<DownloadProgress>? progress, CancellationToken cancellation)
    {
        if (!await gate.WaitAsync(0, cancellation)) throw new InvalidOperationException("An update download is already running.");
        try {
            ValidateUrl(release.Url);
            if (!System.Text.RegularExpressions.Regex.IsMatch(release.Version, @"\A\d{12}\z") ||
                !System.Text.RegularExpressions.Regex.IsMatch(release.Sha256, @"\A[a-fA-F0-9]{64}\z"))
                throw new InvalidDataException("Invalid update version or SHA256.");
            if (release.Size is <= 0 or > MaximumBytes) throw new InvalidDataException("Invalid update size.");
            Directory.CreateDirectory(cache);
            var sources = await OrderedSources(release, progress, cancellation).ConfigureAwait(false);
            for (var index = 0; index < sources.Count; index++) {
                cancellation.ThrowIfCancellationRequested();
                if (sources.Count > 1) progress?.Report(new(0, release.Size, sources[index].Host));
                try { return await DownloadFrom(release, sources[index], progress, cancellation).ConfigureAwait(false); }
                catch (Exception error) when (!cancellation.IsCancellationRequested && index + 1 < sources.Count &&
                    (error is HttpRequestException or TimeoutException || error is IOException and not InvalidDataException)) {
                    // Each attempt deletes its own .part file; never combine bytes across sources.
                }
            }
            throw new IOException("No update download source completed.");
        }
        finally { gate.Release(); }
    }
    async Task<VerifiedUpdate> DownloadFrom(UpdateRelease release, Uri url, IProgress<DownloadProgress>? progress, CancellationToken cancellation)
    {
        string? partial = null;
        try {
            // A unique partial file is never executable. Only a fully verified payload is promoted.
            partial = System.IO.Path.Combine(cache, Guid.NewGuid().ToString("N") + ".part");
            var destination = System.IO.Path.Combine(cache, "BensonMail-Setup-" + release.Version + "-" + release.Sha256.ToLowerInvariant() + ".exe");
            using var request = new HttpRequestMessage(HttpMethod.Get, url);
            request.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true };
            using var headersTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            headersTimeout.CancelAfter(TimeSpan.FromSeconds(45));
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, headersTimeout.Token).ConfigureAwait(false);
            ValidateUrl(response.RequestMessage?.RequestUri ?? url);
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
                    progress?.Report(new(received, total, url.Host));
                }
                await output.FlushAsync(cancellation).ConfigureAwait(false);
            }
            cancellation.ThrowIfCancellationRequested();
            if (received == 0 || total.HasValue && received != total.Value) throw new EndOfStreamException("The update download is incomplete.");
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
    sealed class BrokenReadStream : MemoryStream
    {
        internal BrokenReadStream(byte[] value) : base(value) { }
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellation = default) =>
            Position > 0 ? ValueTask.FromException<int>(new IOException("Synthetic transport disconnected after a prefix")) :
            base.ReadAsync(buffer[..Math.Min(7, buffer.Length)], cancellation);
    }
    sealed class CountedReadStream : MemoryStream
    {
        internal long ReadBytes;
        internal CountedReadStream(byte[] value) : base(value) { }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellation = default)
        {
            var count = await base.ReadAsync(buffer, cancellation);
            ReadBytes += count;
            return count;
        }
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
        var alternate = new Uri("https://mirror.example.invalid/update.exe");
        var multi = release with { Mirrors = new[] { alternate } };
        var fullRequests = new List<string>();
        var probes = new List<CountedReadStream>();
        using (var choice = new UpdateDownload(cache, new FixtureHandler(async (request, token) => {
            if (request.Headers.Range != null) {
                if (request.Headers.Range.ToString() != "bytes=0-262143") throw new InvalidOperationException("Probe exceeded its 256 KiB range");
                await Task.Delay(request.RequestUri!.Host == release.Url.Host ? 200 : 1, token);
                var stream = new CountedReadStream(new byte[ProbeBytes * 2]);
                lock (probes) probes.Add(stream);
                // Deliberately ignore Range: the client must still cap reads and close the response.
                return new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = new StreamContent(stream) };
            }
            fullRequests.Add(request.RequestUri!.Host);
            return Response(request);
        }))) {
            var selected = await choice.Download(multi, null, default);
            Check(fullRequests.SequenceEqual(new[] { alternate.Host }) && probes.Count == 2 && probes.All(stream => stream.ReadBytes == ProbeBytes),
                "Bounded concurrent probes select the faster usable source and fetch exactly one complete package, even when servers ignore Range");
            await VerifyBeforeInstall(selected);
        }
        fullRequests.Clear();
        long failedPrefix = 0;
        using (var fallback = new UpdateDownload(cache, new FixtureHandler(async (request, token) => {
            if (request.Headers.Range != null) {
                await Task.Delay(request.RequestUri!.Host == release.Url.Host ? 200 : 1, token);
                return Response(request);
            }
            fullRequests.Add(request.RequestUri!.Host);
            return request.RequestUri.Host == alternate.Host
                ? new HttpResponseMessage(HttpStatusCode.OK) { RequestMessage = request, Content = new StreamContent(new BrokenReadStream(bytes)) }
                : Response(request);
        }))) {
            var recovered = await fallback.Download(multi, new InlineProgress(value => { if (value.SourceHost == alternate.Host) failedPrefix = Math.Max(failedPrefix, value.Bytes); }), default);
            Check(failedPrefix > 0 && fullRequests.SequenceEqual(new[] { alternate.Host, release.Url.Host }) &&
                File.ReadAllBytes(recovered.Path).SequenceEqual(bytes) && Directory.GetFiles(cache, "*.part").Length == 0,
                "A transport failure after partial bytes falls back to the other source with a fresh file and SHA256; source bytes are never mixed");
        }
        var fullBeforeBodyCancel = 0;
        using var multiBodyCancel = new CancellationTokenSource();
        using (var bodyCancelled = new UpdateDownload(cache, new FixtureHandler((request, _) => {
            if (request.Headers.Range == null) fullBeforeBodyCancel++;
            return Task.FromResult(Response(request));
        }))) {
            try {
                await bodyCancelled.Download(multi, new InlineProgress(value => { if (value.Bytes > 0) multiBodyCancel.Cancel(); }), multiBodyCancel.Token);
                throw new Exception("Multi-source streaming cancellation ignored");
            } catch (OperationCanceledException) { }
            Check(fullBeforeBodyCancel == 1 && Directory.GetFiles(cache, "*.part").Length == 0,
                "Cancellation during the selected-source download deletes its partial file and never starts a fallback transfer");
        }
        var fullAfterProbeCancel = 0;
        using var probeCancel = new CancellationTokenSource();
        using (var cancelledProbe = new UpdateDownload(cache, new FixtureHandler(async (request, token) => {
            if (request.Headers.Range == null) fullAfterProbeCancel++;
            probeCancel.Cancel(); await Task.Delay(1000, token); return Response(request);
        }))) {
            try { await cancelledProbe.Download(multi, null, probeCancel.Token); throw new Exception("Probe cancellation ignored"); }
            catch (OperationCanceledException) { }
            Check(fullAfterProbeCancel == 0 && Directory.GetFiles(cache, "*.part").Length == 0,
                "Cancellation stops every speed probe without starting a complete download or leaving partial files");
        }
        fullRequests.Clear();
        using (var timedProbe = new UpdateDownload(cache, new FixtureHandler(async (request, token) => {
            if (request.Headers.Range != null && request.RequestUri!.Host == release.Url.Host) await Task.Delay(1000, token);
            if (request.Headers.Range == null) fullRequests.Add(request.RequestUri!.Host);
            return Response(request);
        }), TimeSpan.FromMilliseconds(50))) {
            await timedProbe.Download(multi, null, default);
            Check(fullRequests.SequenceEqual(new[] { alternate.Host }), "A timed-out probe does not block a usable alternate source");
        }
        fullRequests.Clear();
        using (var corrupt = new UpdateDownload(cache, new FixtureHandler((request, _) => {
            if (request.Headers.Range == null) fullRequests.Add(request.RequestUri!.Host);
            return Task.FromResult(Response(request));
        }))) {
            try { await corrupt.Download(multi with { Sha256 = new string('0', 64) }, null, default); throw new Exception("Multi-source bad SHA accepted"); }
            catch (InvalidDataException) { }
            Check(fullRequests.Count == 1 && Directory.GetFiles(cache, "*.part").Length == 0,
                "A mirror cannot bypass SHA256 verification; an integrity failure discards the attempt without executing or mixing sources");
        }
        return checks.ToArray();
    }
}
