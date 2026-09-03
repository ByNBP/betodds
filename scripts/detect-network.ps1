<#
  Kaynak sitelere erisimi degerlendirir ve backend/env dosyasini yazar.

  Turkiye'de iki katmanli filtre gorulur:
    1) DNS zehirlenmesi - alan adi ISP'nin engel sunucusuna cozulur
    2) SNI tabanli DPI  - dogru IP'ye baglanilsa bile TLS resetlenir
  Cozum: gercek IP'yi DoH ile bulmak + trafigi ciadpi proxy'sinden gecirmek.
#>
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$envFile = 'backend/env'

# Site adresi TEK YERDEN gelir: backend/env icindeki BETODDS_SITE.
# betandyou surekli alan adi degistiriyor; degisince yalnizca orayi
# guncellemek yeterli olsun diye host listesini oradan tureti yoruz.
$DEFAULT_SITE = 'https://betandyou-8229.pro'

function Read-EnvFile {
    param([string]$Path)
    $map = @{}
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
                $map[$Matches[1]] = $Matches[2].Trim()
            }
        }
    }
    return $map
}

$existing = Read-EnvFile $envFile
$site = if ($existing.BETODDS_SITE) { $existing.BETODDS_SITE } else { $DEFAULT_SITE }
$siteHost = ([Uri]$site).Host
Write-Host "Site: $site"
$hostsToCheck = @($siteHost, 'eventsstat.com')

function Resolve-Doh {
    param([string]$Name, [string]$Provider = 'cloudflare')
    $url = if ($Provider -eq 'google') {
        "https://dns.google/resolve?name=$Name&type=A"
    } else {
        "https://cloudflare-dns.com/dns-query?name=$Name&type=A"
    }
    try {
        $r = Invoke-RestMethod -Uri $url -Headers @{ accept = 'application/dns-json' } -TimeoutSec 15
        return ($r.Answer | Where-Object { $_.type -eq 1 } | Select-Object -First 1).data
    } catch { return $null }
}

function Resolve-Local {
    param([string]$Name)
    try {
        return ([System.Net.Dns]::GetHostAddresses($Name) |
                Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
                Select-Object -First 1).IPAddressToString
    } catch { return $null }
}

Write-Host 'Ag durumu kontrol ediliyor...'
$overrides = @()
foreach ($h in $hostsToCheck) {
    $real  = Resolve-Doh $h
    $check = Resolve-Doh $h 'google'
    $local = Resolve-Local $h

    if (-not $real) {
        Write-Host ("  {0,-24} DoH yaniti yok - atlandi" -f $h); continue
    }
    if ($check -and $check -ne $real) {
        Write-Host ("  {0,-24} iki DoH saglayici farkli yanit verdi ({1} / {2})" -f $h, $real, $check)
    }
    if ($local -and $local -ne $real) {
        Write-Host ("  {0,-24} DNS ZEHIRLENMESI: yerel={1}  gercek={2}" -f $h, $local, $real)
        $overrides += "$h=$real"
    } else {
        Write-Host ("  {0,-24} DNS temiz ({1})" -f $h, $real)
    }
}

$lines = @(
    "# scripts/detect-network.ps1 tarafindan uretildi - $(Get-Date -Format 'yyyy-MM-dd HH:mm')",
    '',
    '# Site adresi. betandyou alan adini sik degistiriyor; degistiginde',
    '# YALNIZCA burayi guncelleyip detect-network.ps1''i tekrar calistirin.',
    "BETODDS_SITE=$site",
    '',
    'BETODDS_POLL=20'
)
if ($overrides.Count -gt 0) { $lines += "BETODDS_DNS_OVERRIDE=$($overrides -join ',')" }
# Proxy adresini docker-compose ezer; burasi yerel calistirma icin.
$lines += 'BETODDS_PROXY=socks5://127.0.0.1:1080'

New-Item -ItemType Directory -Force -Path 'backend' | Out-Null
# .env dosyasi LF ve BOM'suz olmali - konteyner icinde okunuyor
[IO.File]::WriteAllText((Resolve-Path -LiteralPath '.').Path + [IO.Path]::DirectorySeparatorChar + $envFile.Replace('/', [IO.Path]::DirectorySeparatorChar),
    (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))

Write-Host ''
Write-Host "-> $envFile yazildi:"
$lines | ForEach-Object { Write-Host "     $_" }
