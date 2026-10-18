# Public-client Microsoft device-code sign-in. Never print or save bearer tokens.
$ErrorActionPreference = 'Stop'
try {
    Write-Host 'Mail Secretary / 邮件小秘书：获取 Microsoft OAuth2 access token'
    Write-Host 'For Outlook, Hotmail and Microsoft 365 only. / 仅适用于微软邮箱。'
    Write-Host 'First register your own public-client app and grant delegated IMAP permission as described in the guide.'
    Write-Host '请先按教程完成自己的应用注册、公共客户端流及 IMAP 委托权限配置。'
    Write-Host 'This tool does not need your mailbox password or an application secret. / 不要在这里输入邮箱密码或客户端密码。'
    $clientId = (Read-Host 'Application (client) ID / 应用程序(客户端) ID').Trim()
    $parsedId = [Guid]::Empty
    if (-not [Guid]::TryParse($clientId, [ref]$parsedId)) { throw 'Invalid client ID / 客户端 ID 格式不正确。' }
    $tenant = (Read-Host 'Tenant: Enter for consumers (personal account), or enter your organization tenant ID / 个人邮箱直接回车；组织邮箱填租户 ID').Trim()
    if (-not $tenant) { $tenant = 'consumers' }
    $parsedTenant = [Guid]::Empty
    if ($tenant -notin @('consumers', 'organizations', 'common') -and -not [Guid]::TryParse($tenant, [ref]$parsedTenant)) {
        throw 'Invalid tenant ID / 租户 ID 格式不正确。'
    }
    $scope = 'https://outlook.office.com/IMAP.AccessAsUser.All offline_access'
    $base = "https://login.microsoftonline.com/$tenant/oauth2/v2.0"
    $device = Invoke-RestMethod -Method Post -TimeoutSec 30 -Uri "$base/devicecode" -Body @{client_id=$clientId;scope=$scope}
    Write-Host ''
    Write-Host $device.message
    Write-Host 'Open the Microsoft URL above in your browser and enter the one-time code. Verify the app is yours before approving.'
    Write-Host '请在浏览器打开上面的微软网址、输入一次性代码，确认是你注册的应用后再授权。不要关闭本窗口。'
    $until = (Get-Date).AddSeconds([int]$device.expires_in)
    $interval = 5
    if ($device.interval) { $interval = [Math]::Max(1, [int]$device.interval) }
    $token = $null
    while ((Get-Date) -lt $until) {
        Start-Sleep -Seconds $interval
        try {
            $token = Invoke-RestMethod -Method Post -TimeoutSec 30 -Uri "$base/token" -Body @{grant_type='urn:ietf:params:oauth:grant-type:device_code';client_id=$clientId;device_code=$device.device_code}
            break
        } catch {
            try { $failure = $_.ErrorDetails.Message | ConvertFrom-Json } catch { throw 'Microsoft sign-in request failed / 微软登录请求失败，请检查网络后重试。' }
            if ($failure.error -eq 'authorization_pending') { continue }
            if ($failure.error -eq 'slow_down') { $interval += 5; continue }
            # Show the error code only; never dump the raw response or token values.
            $errorCode = [string]$failure.error
            if ($errorCode -notmatch '^[a-zA-Z0-9_]{1,80}$') { $errorCode = 'sign_in_failed' }
            throw "Microsoft sign-in failed / 微软登录失败：$errorCode. Ask your administrator to check app permissions and policy / 请管理员检查应用权限与策略。"
        }
    }
    if (-not $token.access_token) { throw 'Sign-in expired; start again / 登录超时，请重新运行。' }
    $token.access_token | Set-Clipboard
    Write-Host ''
    Write-Host 'Access token copied. Paste it ONLY into Mail Secretary > OAuth2 access token, save, and test.'
    Write-Host '访问令牌已复制。只粘贴到邮件小秘书的“OAuth2 访问令牌”框，保存并测试。'
    Write-Host 'Then copy ordinary text to clear the clipboard. Tokens expire; run this tool again when needed.'
    Write-Host '完成后复制普通文字覆盖剪贴板。令牌会过期，届时需要重新获取；本工具不自动续期。'
    $token = $null
} catch {
    Write-Host ('Unable to get token / 未能获取令牌：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
