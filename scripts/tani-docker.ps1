<#
  "Imaj derlenemedi / depolara erisilemiyor" teshisi.

  Tarayicinin calisiyor olmasi konteynerin de calistigi anlamina gelmez:
  Docker Desktop (WSL2) kendi ag yiginini ve DNS'ini kullanir. En sik sorun,
  konteyner icinden DNS cozumunun yapilamamasidir.

  Kullanim:  powershell -ExecutionPolicy Bypass -File scripts\tani-docker.ps1
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
    Write-Host ("  {0,-34} " -f $k) -NoNewline; Write-Host $v -ForegroundColor $c
}

$HOSTS = @('dl-cdn.alpinelinux.org', 'pypi.org', 'registry.npmjs.org')

Write-Host ''
Write-Host '=== Docker ag teshisi ===' -ForegroundColor Cyan
Write-Host ''

# --- 1) host tarafi ------------------------------------------------------
Write-Host '  [host tarafi]'
$hostOk = $true
foreach ($h in $HOSTS) {
    try {
        $ip = ([Net.Dns]::GetHostAddresses($h) |
               Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
               Select-Object -First 1).IPAddressToString
        Line $h $ip $true
    } catch { Line $h 'cozulemedi' $false; $hostOk = $false }
}

# --- 2) docker motoru ----------------------------------------------------
Write-Host ''
Write-Host '  [docker]'
$info = Invoke-Native docker @('info', '--format', '{{.ServerVersion}}')
Line 'motor' $(if ($info.ExitCode -eq 0) { $info.Output.Trim() } else { 'yanit yok' }) ($info.ExitCode -eq 0)
if ($info.ExitCode -ne 0) {
    Write-Host ''
    Write-Host '  Docker motoru calismiyor. Once Docker Desktop''i baslatin.' -ForegroundColor Yellow
    exit 1
}

# --- 3) imaj cekilebiliyor mu -------------------------------------------
Write-Host ''
Write-Host '  [konteyner tarafi]'
Write-Host '  alpine imaji cekiliyor (kucuk test)...'
$pull = Invoke-Native docker @('pull', 'alpine:3.20')
$pullOk = ($pull.ExitCode -eq 0)
Line 'docker pull alpine:3.20' $(if ($pullOk) { 'basarili' } else { 'BASARISIZ' }) $pullOk
if (-not $pullOk -and $pull.Error) {
    ($pull.Error -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 3) |
        ForEach-Object { Write-Host "      $($_.Trim())" -ForegroundColor DarkGray }
}

$dnsOk = $false
if ($pullOk) {
    $r = Invoke-Native docker @('run', '--rm', 'alpine:3.20', 'nslookup', 'pypi.org')
    $dnsOk = ($r.ExitCode -eq 0 -and $r.Output -match 'Address')
    Line 'konteyner icinden DNS' $(if ($dnsOk) { 'calisiyor' } else { 'CALISMIYOR' }) $dnsOk
    $r2 = Invoke-Native docker @('run', '--rm', 'alpine:3.20', 'sh', '-c',
                                 'apk update >/dev/null 2>&1 && echo OK')
    $repoOk = ($r2.Output -match 'OK')
    Line 'konteyner icinden apk deposu' $(if ($repoOk) { 'erisilebiliyor' } else { 'ERISILEMIYOR' }) $repoOk
}

# --- sonuc ---------------------------------------------------------------
Write-Host ''
if ($pullOk -and $dnsOk) {
    Write-Host '  Konteyner agi saglikli gorunuyor.' -ForegroundColor Green
    Write-Host '  Derleme yine de basarisizsa hatanin tam metnini paylasin.'
} else {
    Write-Host '=== EN OLASI COZUM: Docker DNS ayari ===' -ForegroundColor Yellow
    Write-Host @'

  Docker Desktop > Settings > Docker Engine bolumundeki JSON'a "dns" ekleyin:

      {
        "builder": { "gc": { "defaultKeepStorage": "20GB", "enabled": true } },
        "experimental": false,
        "dns": ["8.8.8.8", "1.1.1.1"]
      }

  "Apply & restart" deyin, sonra bu teshisi tekrar calistirin.

  Ise yaramazsa sirasiyla:
    * VPN / kurumsal proxy varsa kapatip deneyin. Proxy zorunluysa:
      Settings > Resources > Proxies bolumune girin.
    * Antivirus (Kaspersky, ESET, Comodo) WSL agini engelleyebiliyor;
      gecici olarak kapatip deneyin.
    * WSL'i sifirlayin (yonetici PowerShell):
        wsl --shutdown
      ardindan Docker Desktop'i yeniden baslatin.
    * Settings > Resources > Network > "Use kernel networking for UDP"
      secenegini tersine cevirip deneyin.
'@
}

Write-Host ''
Write-Host '=== Ag hic duzelmezse: hazir imajlar ===' -ForegroundColor Cyan
Write-Host @'
  Imajlar erisimi olan bir makinede uretilip bu projeye tasinabilir:

      docker save betodds:latest       | gzip > images\betodds.tar.gz
      docker save betodds-proxy:latest | gzip > images\betodds-proxy.tar.gz

  Dosyalari proje icindeki images\ klasorune koyun ve KURULUM.bat'i tekrar
  calistirin; script derlemek yerine bunlari yukler (etiketleri de duzeltir).
'@
Write-Host ''
