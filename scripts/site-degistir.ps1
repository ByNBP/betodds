<#
  Kaynak site adresini degistirir ve GERCEKTEN calistigini dogrular.

  betandyou aynalari sik degisiyor. Bu betik:
    1. Yeni adresi normallestirir
    2. DoH ile gercek IP'yi bulur, yerel DNS zehirliyse override yazar
    3. API'yi (sayfa degil) proxy uzerinden dener - Success=true mi
    4. Yapilandirilan ligin hala veri dondurdugunu kontrol eder
    5. backend/env dosyasini gunceller (diger satirlari korur)
    6. Servisi yeniden olusturur ve toplayicinin duzeldigini dogrular

  Kullanim:
    powershell -ExecutionPolicy Bypass -File scripts\site-degistir.ps1
    ... -Site https://betandyou-1234.pro
    ... -Site betandyou-1234.pro -SkipRestart
#>
param(
    [string]$Site,
    [switch]$SkipRestart
)

$ErrorActionPreference = 'Continue'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
Set-Location (Join-Path $PSScriptRoot '..')

$ENV_FILE = 'backend/env'

function Say  { param($m, $c = 'Gray') Write-Host $m -ForegroundColor $c }
function Line { param($k, $v, $good = $null)
    $c = if ($good -eq $true) { 'Green' } elseif ($good -eq $false) { 'Red' } else { 'Gray' }
    Write-Host ("  {0,-26} " -f $k) -NoNewline; Write-Host $v -ForegroundColor $c
}
function Fail { param($m) Write-Host ''; Write-Host "HATA: $m" -ForegroundColor Red; exit 1 }

function Invoke-Native {
    param([Parameter(Mandatory)][string]$File, [string[]]$Arguments = @())
    $errFile = [IO.Path]::GetTempFileName(); $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $File @Arguments 2>$errFile | Out-String
        [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $out
                           Error = (Get-Content $errFile -Raw -ErrorAction SilentlyContinue) }
    } catch { [pscustomobject]@{ ExitCode = -1; Output = ''; Error = $_.Exception.Message } }
    finally { $ErrorActionPreference = $prev; Remove-Item $errFile -ErrorAction SilentlyContinue }
}

function Read-EnvFile {
    param([string]$Path)
    $map = [ordered]@{}
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') { $map[$Matches[1]] = $Matches[2].Trim() }
        }
    }
    return $map
}

function Write-EnvFile {
    param([string]$Path, $Map)
    $lines = @("# scripts/site-degistir.ps1 - $(Get-Date -Format 'yyyy-MM-dd HH:mm')", '')
    foreach ($k in $Map.Keys) { $lines += "$k=$($Map[$k])" }
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    # LF ve BOM'suz: dosya konteyner icinde okunuyor
    [IO.File]::WriteAllText((Join-Path (Get-Location) $Path),
        (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
}

function Resolve-Doh {
    param([string]$Name, [string]$Provider = 'cloudflare')
    $url = if ($Provider -eq 'google') { "https://dns.google/resolve?name=$Name&type=A" }
           else { "https://cloudflare-dns.com/dns-query?name=$Name&type=A" }
    try {
        $r = Invoke-RestMethod -Uri $url -Headers @{ accept = 'application/dns-json' } -TimeoutSec 15
        return ($r.Answer | Where-Object { $_.type -eq 1 } | Select-Object -First 1).data
    } catch { return $null }
}

# --------------------------------------------------------------- adres alma
Write-Host ''
Write-Host '=== Site adresi degistirme ===' -ForegroundColor Cyan
Write-Host ''

$envMap = Read-EnvFile $ENV_FILE
$current = if ($envMap.BETODDS_SITE) { $envMap.BETODDS_SITE } else { 'https://betandyou-1268.pro' }
Line 'mevcut adres' $current

if (-not $Site) {
    Write-Host ''
    Write-Host '  Yeni adresi girin (tarayicinizda acilan adres).'
    Write-Host '  Ornek: https://betandyou-1234.pro   ya da   betandyou-1234.pro'
    $Site = Read-Host '  Yeni adres'
}
if (-not $Site) { Fail 'adres girilmedi' }

# Normallestir: sema ekle, yol/sondaki slash'i at
$Site = $Site.Trim()
if ($Site -notmatch '^https?://') { $Site = "https://$Site" }
try { $uri = [Uri]$Site } catch { Fail "gecersiz adres: $Site" }
$Site = "https://$($uri.Host)"
$siteHost = $uri.Host
Line 'yeni adres' $Site
if ($Site -eq $current) { Say '  (adres zaten bu - yine de dogrulanacak)' }

# --------------------------------------------------------------- DNS
Write-Host ''
$real = Resolve-Doh $siteHost
$cross = Resolve-Doh $siteHost 'google'
if (-not $real) { Fail "$siteHost DoH ile cozulemedi. Adres dogru mu?" }
Line 'gercek IP (DoH)' $real $true
if ($cross -and $cross -ne $real) { Say "  not: ikinci saglayici farkli yanit verdi ($cross)" 'Yellow' }

$local = $null
try {
    $local = ([Net.Dns]::GetHostAddresses($siteHost) |
              Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
              Select-Object -First 1).IPAddressToString
} catch { }
$poisoned = ($local -and $local -ne $real)
Line 'yerel DNS' $(if ($local) { $local } else { 'cozulemedi' }) (-not $poisoned)
if ($poisoned) { Say '  -> DNS zehirlenmesi: override yazilacak' 'Yellow' }

# --------------------------------------------------------------- API testi
Write-Host ''
Write-Host '  API deneniyor (sayfa degil, gercek veri ucu)...'

$champ = 2986291
if (Test-Path 'data/leagues.json') {
    try {
        $lg = Get-Content 'data/leagues.json' -Raw | ConvertFrom-Json
        if ($lg -and $lg[0].champ_id) { $champ = $lg[0].champ_id }
    } catch { }
}
$api = "$Site/service-api/LiveFeed/Get1x2_VZip?champs=$champ&count=50&lng=tr&mode=4&country=1&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"
$resolve = if ($poisoned) { "$siteHost`:443:$real" } else { $null }

$hasDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)
$body = $null

if ($hasDocker) {
    $a = @('compose', 'exec', '-T', 'betodds', 'curl', '-s', '--max-time', '25', '--socks5', 'proxy:1080')
    if ($resolve) { $a += @('--resolve', $resolve) }
    $a += @('-A', 'Mozilla/5.0', $api)
    $r = Invoke-Native docker $a
    if ($r.ExitCode -eq 0 -and $r.Output) { $body = $r.Output }
}
# DIKKAT: PowerShell 5.1'de "curl" Invoke-WebRequest'in TAKMA ADIdir, program
# degil. Bu yuzden yalnizca CommandType=Application olani kabul ediyoruz.
$curlExe = @('curl.exe', 'curl') |
    ForEach-Object { Get-Command $_ -CommandType Application -ErrorAction SilentlyContinue } |
    Select-Object -First 1
if (-not $body -and $curlExe) {
    $a = @('-s', '--max-time', '25')
    if ($envMap.BETODDS_PROXY -match 'socks5://(.+)') { $a += @('--socks5', $Matches[1]) }
    if ($resolve) { $a += @('--resolve', $resolve) }
    $a += @('-A', 'Mozilla/5.0', $api)
    $r = Invoke-Native $curlExe.Source $a
    if ($r.ExitCode -eq 0 -and $r.Output) { $body = $r.Output }
}

if (-not $body) {
    Line 'API' 'yanit alinamadi' $false
    Say ''
    Say '  Adres dogru olsa bile proxy/DPI stratejisi tutmuyor olabilir.' 'Yellow'
    Say '  Once su betigi calistirin:  scripts\tani-veri.ps1' 'Yellow'
    Fail 'dogrulanamadi - backend/env DEGISTIRILMEDI'
}

$data = $null
try { $data = $body | ConvertFrom-Json } catch { }
if (-not $data -or -not $data.Success) {
    Line 'API' 'JSON gelmedi / Success=false' $false
    Say "  ilk 200 karakter: $($body.Substring(0, [Math]::Min(200, $body.Length)))" 'DarkGray'
    Fail 'dogrulanamadi - backend/env DEGISTIRILMEDI'
}
Line 'API' 'Success=true' $true
$count = @($data.Value).Count
Line "lig $champ" "$count mac" ($count -gt 0)
if ($count -gt 0) {
    @($data.Value) | Select-Object -First 4 | ForEach-Object {
        Write-Host "      $($_.O1) vs $($_.O2)" -ForegroundColor DarkGray
    }
} else {
    Say ''
    Say "  UYARI: adres calisiyor ama lig $champ bos donuyor." 'Yellow'
    Say '  Lig kimligi de degismis olabilir. data\leagues.json icindeki' 'Yellow'
    Say '  champ_id degerini guncellemeniz gerekebilir.' 'Yellow'
}

# --------------------------------------------------------------- yaz
Write-Host ''
$envMap.BETODDS_SITE = $Site
if ($poisoned) {
    # Diger host'lar icin var olan eslemeleri koru, bu host'unkini tazele
    $pairs = @()
    if ($envMap.BETODDS_DNS_OVERRIDE) {
        $pairs = ($envMap.BETODDS_DNS_OVERRIDE -split ',') |
                 Where-Object { $_ -and ($_ -split '=')[0].Trim() -ne $siteHost }
    }
    $pairs += "$siteHost=$real"
    $envMap.BETODDS_DNS_OVERRIDE = ($pairs -join ',')
} elseif ($envMap.BETODDS_DNS_OVERRIDE) {
    $pairs = ($envMap.BETODDS_DNS_OVERRIDE -split ',') |
             Where-Object { $_ -and ($_ -split '=')[0].Trim() -ne $siteHost }
    if ($pairs) { $envMap.BETODDS_DNS_OVERRIDE = ($pairs -join ',') }
    else { $envMap.Remove('BETODDS_DNS_OVERRIDE') }
}
if (-not $envMap.BETODDS_POLL) { $envMap.BETODDS_POLL = '20' }
if (-not $envMap.BETODDS_PROXY) { $envMap.BETODDS_PROXY = 'socks5://127.0.0.1:1080' }

Write-EnvFile $ENV_FILE $envMap
Say "  $ENV_FILE guncellendi:" 'Green'
Get-Content $ENV_FILE | Where-Object { $_ -and $_ -notmatch '^#' } |
    ForEach-Object { Write-Host "     $_" }

# --------------------------------------------------------------- yeniden baslat
if ($SkipRestart -or -not $hasDocker) {
    Write-Host ''
    Say '  Degisikligin etkili olmasi icin servisi yeniden baslatin:'
    Say '    docker compose up -d --no-build --force-recreate betodds'
    exit 0
}

Write-Host ''
Write-Host '  Servis yeniden olusturuluyor...'
Invoke-Native docker @('compose', 'up', '-d', '--no-build', '--force-recreate', 'betodds') | Out-Null

$before = $null
try { $before = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 5 } catch { }
Write-Host '  Toplayici izleniyor (40 sn)...'
$ok = $false
foreach ($i in 1..20) {
    Start-Sleep -Seconds 2
    try {
        $h = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 3
        if ($h.collector.poll_count -gt 0 -and -not $h.collector.last_error) { $ok = $true; break }
    } catch { }
}
Write-Host ''
if ($ok) {
    Write-Host '  TAMAM - toplayici hatasiz calisiyor.' -ForegroundColor Green
    Write-Host ("  {0} mac, {1} arsiv, {2} oran kaydi" -f $h.db.matches, $h.db.snapshots, $h.db.ticks)
    Write-Host '  http://localhost:8000'
} else {
    Write-Host '  Toplayici hala hata veriyor:' -ForegroundColor Yellow
    if ($h.collector.last_error) { Write-Host "    $($h.collector.last_error)" }
    Write-Host '  Siradaki adim:  scripts\tani-veri.ps1'
}
Write-Host ''
