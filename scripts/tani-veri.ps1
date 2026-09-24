<#
  "Proje ayakta ama veri gelmiyor" teshisi.

  Sirasiyla: toplayici hata veriyor mu -> proxy calisiyor mu ->
  hangi DPI stratejisi bu agda tutuyor. Calisan strateji bulunursa
  .env dosyasina yazilir ve proxy yeniden olusturulur.

  Kullanim:  powershell -ExecutionPolicy Bypass -File scripts\tani-veri.ps1
#>
$ErrorActionPreference = 'Continue'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
Set-Location (Join-Path $PSScriptRoot '..')

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
function Line { param($k, $v, $good = $null)
    $c = if ($good -eq $true) { 'Green' } elseif ($good -eq $false) { 'Red' } else { 'Gray' }
    Write-Host ("  {0,-30} " -f $k) -NoNewline; Write-Host $v -ForegroundColor $c
}

Write-Host ''
Write-Host '=== Veri akisi teshisi ===' -ForegroundColor Cyan
Write-Host ''

# --- 1) Toplayici gercekten calisiyor mu --------------------------------
$h1 = $null
try { $h1 = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 5 } catch { }
if (-not $h1) {
    Line 'uygulama' 'yanit vermiyor' $false
    Write-Host '  Once servisleri baslatin:  docker compose up -d'
    exit 1
}
Line 'uygulama' 'calisiyor' $true
Line 'toplayici' $(if ($h1.collector.running) { 'aktif' } else { 'DURMUS' }) $h1.collector.running
Line 'poll sayisi' $h1.collector.poll_count
Line 'veritabani' ("{0} mac, {1} arsiv, {2} tick" -f $h1.db.matches, $h1.db.snapshots, $h1.db.ticks)
if ($h1.collector.last_error) {
    Write-Host ''
    Write-Host '  Toplayici hatasi:' -ForegroundColor Yellow
    Write-Host "    $($h1.collector.last_error)" -ForegroundColor Yellow
}

# --- 2) 25 saniyede sayaclar artiyor mu ---------------------------------
Write-Host ''
Write-Host '  25 saniye izleniyor...'
Start-Sleep -Seconds 25
$h2 = $null
try { $h2 = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 5 } catch { }
$pollDelta = if ($h2) { $h2.collector.poll_count - $h1.collector.poll_count } else { 0 }
$tickDelta = if ($h2) { $h2.db.ticks - $h1.db.ticks } else { 0 }
Line 'yeni poll' $pollDelta ($pollDelta -gt 0)
Line 'yeni oran kaydi (tick)' $tickDelta ($tickDelta -gt 0)

if ($tickDelta -gt 0) {
    Write-Host ''
    Write-Host '  VERI AKIYOR.' -ForegroundColor Green
    Write-Host '  Ekranda guncellenmiyorsa tarayicida sayfayi yenileyin (Ctrl+F5).'
    Write-Host '  Canli akis (SSE) bazi kurumsal proxy''lerde tamponlanabiliyor;'
    Write-Host '  sayfa 15 saniyede bir kendini yine de tazeler.'
    exit 0
}

# --- 3) Proxy ve strateji ------------------------------------------------
Write-Host ''
Write-Host '  Veri gelmiyor. Proxy stratejisi deneniyor...' -ForegroundColor Yellow
Write-Host ''

$ps = Invoke-Native docker @('compose', 'ps', '--format', '{{.Service}} {{.State}}')
$ps.Output -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Host "    $($_.Trim())" }

# Site ve IP eslemesi backend/env'den okunur (tek kaynak).
$envMap = @{}
if (Test-Path 'backend/env') {
    Get-Content 'backend/env' | ForEach-Object {
        if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') { $envMap[$Matches[1]] = $Matches[2].Trim() }
    }
}
$site = if ($envMap.BETODDS_SITE) { $envMap.BETODDS_SITE } else { 'https://betandyou-1268.pro' }
$siteHost = ([Uri]$site).Host
$api = "$site/service-api/LiveFeed/Get1x2_VZip?champs=2986291&count=50&lng=tr&mode=4&country=1&getEmpty=true&virtualSports=true&noFilterBlockEvent=true"

$ip = $null
if ($envMap.BETODDS_DNS_OVERRIDE) {
    foreach ($pair in $envMap.BETODDS_DNS_OVERRIDE -split ',') {
        $kv = $pair -split '=', 2
        if ($kv.Count -eq 2 -and $kv[0].Trim() -eq $siteHost) { $ip = "$siteHost:443:$($kv[1].Trim())" }
    }
}
if (-not $ip) {
    # Override yoksa yerel DNS kullanilsin diye --resolve'u atlayacagiz
    $ip = ''
}
Write-Host ''
Write-Host "    site: $site"
Write-Host "    IP eslemesi: $(if ($ip) { $ip } else { '(yok - yerel DNS)' })"

# Stratejiler: ilki mevcut, digerleri alternatif
$strategies = @('-o 1+s', '-q 1+s', '-r 1+s', '-s 1+s', '-d 1+s', '-f 1+s',
                '-o 2', '-q 3+s', '-r 1+s -s 1+s')
$found = $null
foreach ($st in $strategies) {
    Write-Host ("    {0,-16} " -f $st) -NoNewline
    $env:CIADPI_ARGS = $st
    Invoke-Native docker @('compose', 'up', '-d', '--no-build', '--force-recreate', 'proxy') | Out-Null
    Start-Sleep -Seconds 3
    $curlArgs = @('compose', 'exec', '-T', 'betodds', 'curl', '-s',
                  '--max-time', '20', '--socks5', 'proxy:1080')
    if ($ip) { $curlArgs += @('--resolve', $ip) }
    $curlArgs += @('-A', 'Mozilla/5.0', '-o', '/dev/null', '-w', '%{http_code}', $api)
    $r = Invoke-Native docker $curlArgs
    $code = ($r.Output -replace '\D', '')
    if ($code -eq '200') { Write-Host 'CALISIYOR' -ForegroundColor Green; $found = $st; break }
    else { Write-Host "basarisiz (HTTP $code)" -ForegroundColor DarkGray }
}

Write-Host ''
if ($found) {
    # .env dosyasina yaz - compose bunu kendiliginden okur
    $envLines = @()
    if (Test-Path '.env') {
        $envLines = Get-Content '.env' | Where-Object { $_ -notmatch '^\s*CIADPI_ARGS\s*=' }
    }
    $envLines += "CIADPI_ARGS=$found"
    [IO.File]::WriteAllText((Join-Path (Get-Location) '.env'),
        (($envLines -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
    Write-Host "  Calisan strateji: $found" -ForegroundColor Green
    Write-Host '  .env dosyasina yazildi; proxy bu ayarla calisiyor.'
    Write-Host '  Birkac dakika icinde veri akmaya baslamali.'
} else {
    Write-Host '  Hicbir strateji tutmadi.' -ForegroundColor Red
    Write-Host ''
    Write-Host '  Muhtemel sebepler:'
    Write-Host '    * DNS eslemesi eskimis olabilir. Yenilemek icin:'
    Write-Host '        del backend\env'
    Write-Host '        powershell -ExecutionPolicy Bypass -File scripts\detect-network.ps1'
    Write-Host '        docker compose up -d --no-build --force-recreate betodds'
    Write-Host '    * Site adresi degismis olabilir. backend\env icindeki'
    Write-Host '      BETODDS_SITE satirini yeni adresle degistirin, sonra:'
    Write-Host '        del backend\env  (ya da sadece BETODDS_SITE satirini duzenleyin)'
    Write-Host '        docker compose up -d --no-build --force-recreate betodds'
    Write-Host '    * Kurumsal ag / VPN tum trafigi engelliyor olabilir.'
    Write-Host ''
    Write-Host '  Son 10 toplayici logu:'
    try {
        (Invoke-RestMethod 'http://localhost:8000/api/logs?limit=10' -TimeoutSec 5) |
            ForEach-Object { Write-Host "    [$($_.level)] $($_.message)" }
    } catch { }
}
Write-Host ''
