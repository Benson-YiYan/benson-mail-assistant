using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Security.Authentication;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace BensonMail;

sealed class UpdateTransport : IDisposable
{
    internal const string ApiUrl = "https://api.github.com/repos/Benson-YiYan/benson-mail-updates/contents/manifest.json?ref=main";
    readonly HttpClient client;
    internal string? LastSource { get; private set; }
    internal static HttpClientHandler SystemHandler() => new() {
        // Keep the Windows/default proxy and certificate trust behavior. No custom certificate callback.
        UseProxy = true, Proxy = null, SslProtocols = SslProtocols.None
    };
    internal UpdateTransport(HttpMessageHandler? handler = null)
    {
        client = new HttpClient(handler ?? SystemHandler()) { Timeout = TimeSpan.FromSeconds(10), MaxResponseContentBufferSize = 512 * 1024 };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("MailSecretary/" + UpdateClient.InstalledVersion);
    }
    internal async Task<string> Fetch()
    {
        var failures = new List<Exception>();
        foreach (var endpoint in new[] { UpdateClient.ManifestUrl, ApiUrl }) {
            try {
                using var request = new HttpRequestMessage(HttpMethod.Get, endpoint);
                request.Headers.CacheControl = new CacheControlHeaderValue { NoCache = true };
                request.Headers.Accept.ParseAdd(endpoint == ApiUrl ? "application/vnd.github.raw+json" : "application/json");
                using var response = await client.SendAsync(request, HttpCompletionOption.ResponseContentRead);
                if ((response.RequestMessage?.RequestUri ?? request.RequestUri)!.Scheme != Uri.UriSchemeHttps)
                    throw new HttpRequestException("Update source redirected to a non-HTTPS URL.");
                response.EnsureSuccessStatusCode();
                var body = await response.Content.ReadAsStringAsync();
                LastSource = endpoint;
                return body;
            }
            catch (Exception error) when (error is HttpRequestException || error is OperationCanceledException || error is IOException) {
                var cause = error is OperationCanceledException ? new TimeoutException("Update source timed out after 10 seconds.", error) : error;
                failures.Add(new HttpRequestException(endpoint, cause));
            }
        }
        throw new AggregateException("Both HTTPS update sources failed.", failures);
    }
    internal static string ErrorDetails(Exception error, string language)
    {
        var output = new StringBuilder();
        var timeout = false;
        void Visit(Exception current, int depth)
        {
            if (depth > 12 || output.Length > 10000) return;
            if (current is TimeoutException || current is OperationCanceledException) timeout = true;
            output.Append(' ', depth * 2).Append(current.GetType().Name).Append(": ").Append(current.Message)
                .Append(" [0x").Append(current.HResult.ToString("X8")).Append(']');
            if (current is Win32Exception native) output.Append(" Win32=").Append(native.NativeErrorCode);
            output.AppendLine();
            if (current is AggregateException aggregate) foreach (var inner in aggregate.InnerExceptions) Visit(inner, depth + 1);
            else if (current.InnerException != null) Visit(current.InnerException, depth + 1);
        }
        Visit(error, 0);
        var english = language == "en";
        var summary = timeout
            ? (english ? "The update request timed out (10 seconds per source)." : "更新请求超时（每个入口最多 10 秒）。")
            : (english ? "Unable to complete the update check. Check your network, system clock and proxy settings." : "无法完成更新检查。可检查网络、系统时间和代理设置。");
        return summary + Environment.NewLine + (english ? "Technical details:" : "底层错误详情：") + Environment.NewLine + output.ToString().Trim();
    }
    public void Dispose() => client.Dispose();
    sealed class FixtureHandler : HttpMessageHandler
    {
        readonly Func<HttpRequestMessage, Task<HttpResponseMessage>> respond;
        internal FixtureHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> response) { respond = response; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => respond(request);
    }
    internal static async Task<string[]> OfflineTests()
    {
        var checks = new List<string>(); var requests = new List<string>();
        using (var system = SystemHandler()) {
            if (!system.UseProxy || system.Proxy != null || system.ServerCertificateCustomValidationCallback != null || system.SslProtocols != SslProtocols.None)
                throw new InvalidOperationException("Update TLS and system proxy policy was changed");
            checks.Add("Windows default proxy and strict system certificate validation retained; no TLS bypass or forced protocol downgrade");
        }
        using (var transport = new UpdateTransport(new FixtureHandler(request => {
            requests.Add(request.RequestUri!.AbsoluteUri);
            if (request.Headers.CacheControl?.NoCache != true) throw new InvalidOperationException("Missing update cache revalidation header");
            if (request.RequestUri.Host == "raw.githubusercontent.com")
                throw new HttpRequestException("Synthetic SSL connection failure", new AuthenticationException("Synthetic certificate validation failed", new Win32Exception(12345)));
            if (!request.Headers.Accept.ToString().Contains("application/vnd.github.raw+json") || !request.Headers.UserAgent.ToString().StartsWith("MailSecretary/"))
                throw new InvalidOperationException("Missing GitHub API headers");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("fixture manifest") });
        }))) {
            if (await transport.Fetch() != "fixture manifest" || requests.Count != 2 || transport.LastSource != ApiUrl)
                throw new InvalidOperationException("TLS failure did not fall back to API");
            checks.Add("Injected primary TLS failure falls back to GitHub API with raw Accept and versioned User-Agent");
        }
        using (var transport = new UpdateTransport(new FixtureHandler(request => throw new HttpRequestException("Synthetic SSL failure", new AuthenticationException("Untrusted synthetic certificate", new Win32Exception(12345)))))) {
            try { await transport.Fetch(); throw new InvalidOperationException("Both failures were ignored"); }
            catch (AggregateException error) {
                var text = ErrorDetails(error, "zh");
                if (!text.Contains(UpdateClient.ManifestUrl) || !text.Contains(ApiUrl) || !text.Contains("AuthenticationException") || !text.Contains("Win32=12345") || !text.Contains("底层错误详情"))
                    throw new InvalidOperationException("Nested endpoint diagnostics were lost");
                if (!ErrorDetails(error, "en").Contains("Technical details")) throw new InvalidOperationException("English diagnostics missing");
            }
            checks.Add("Both endpoint failures retain recursive AuthenticationException and Win32 details in Chinese and English");
        }
        using (var transport = new UpdateTransport(new FixtureHandler(request => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
            Content = new StringContent("unsafe redirect fixture"), RequestMessage = new HttpRequestMessage(HttpMethod.Get, "http://unsafe.example.invalid/manifest.json")
        })))) {
            try { await transport.Fetch(); throw new InvalidOperationException("Non-HTTPS redirect was accepted"); }
            catch (AggregateException error) {
                if (!ErrorDetails(error, "en").Contains("non-HTTPS")) throw new InvalidOperationException("HTTPS redirect rejection details missing");
            }
            checks.Add("Final response URL must remain HTTPS after redirects; no-cache requested on both update sources");
        }
        var timeoutText = ErrorDetails(new TimeoutException("Synthetic timeout"), "zh");
        if (!timeoutText.Contains("10 秒")) throw new InvalidOperationException("Timeout limit missing");
        checks.Add("Timeout diagnostics state the ten-second limit explicitly");
        return checks.ToArray();
    }
    internal static async Task<int> NetworkProbe(string resultPath)
    {
        try {
            using var transport = new UpdateTransport();
            var release = UpdateClient.Parse(await transport.Fetch(), "en");
            File.WriteAllText(resultPath, JsonSerializer.Serialize(new { ok = true, source = transport.LastSource, version = release.Version,
                strict_tls = true, windows_system_proxy = true, reads_mail = false, ai_calls = 0 }));
            return 0;
        }
        catch (Exception error) {
            File.WriteAllText(resultPath, JsonSerializer.Serialize(new { ok = false, error = ErrorDetails(error, "en") }));
            return 1;
        }
    }
}
