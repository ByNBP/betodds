<#
  BetOdds - Windows'ta tek dosyadan kurulum ve calistirma.

  Yaptigi is sirayla:
    1. Gerekli yazilimlari kurar (Docker Desktop; olmazsa Python + Node)
    2. Ag durumunu tespit edip backend/env yazar
    3. Projeyi derler
    4. Calistirir, saglik kontrolu yapar ve tarayiciyi acar

  Kullanim:
    KURULUM.bat                       (cift tiklayin)
    powershell -ExecutionPolicy Bypass -File KURULUM.ps1
    ... -Native      Docker yerine yerel Python kurulumunu zorlar
    ... -SkipInstall Hicbir sey kurmaz, sadece derleyip calistirir
#>
param(
    [switch]$Native,
    [switch]$SkipInstall,
    # DPI bypass stratejisi. Bu ag icin dogrulanan: -r 1+s
    # Tutmazsa denenecekler: '-o 1+s', '-q 1+s'
    [string]$ProxyArgs = '-r 1+s'
)

$ErrorActionPreference = 'Stop'
# PowerShell 7.3+ bu ayarla native komutun sifir olmayan cikis kodunu
# kendiliginden hataya cevirebiliyor; kendi kontrollerimiz calissin diye kapatiyoruz.
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
Set-Location $PSScriptRoot

$APP_URL = 'http://localhost:8000'

function Say  { param($m, $c = 'Gray')  Write-Host $m -ForegroundColor $c }
function Head { param($m) Write-Host ''; Write-Host $m -ForegroundColor Cyan }
function Warn { param($m) Write-Host "  UYARI: $m" -ForegroundColor Yellow }
function Fail {
    param($m)
    Write-Host ''
    Write-Host "HATA: $m" -ForegroundColor Red
    Write-Host ''
    Write-Host 'Pencere kapanmasin diye bekleniyor - Enter ile cikin.'
    Read-Host | Out-Null
    exit 1
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# winget ile kurulan araclar ayni oturumun PATH'ine dusmez; kayit defterinden tazeliyoruz.
function Update-PathFromRegistry {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($m, $u) | Where-Object { $_ }) -join ';'
}

function Have { param($n) [bool](Get-Command $n -ErrorAction SilentlyContinue) }

<#
  Native komutlari calistirmanin guvenli yolu.

  DIKKAT: Windows'un yerlesik PowerShell 5.1'inde "komut 2>&1 | Out-Null"
  kalibi, $ErrorActionPreference='Stop' iken PATLAR: stderr satirlari
  pipeline'a ErrorRecord olarak dusuyor ve sonlandirici hataya donusuyor.
  docker normal calisirken bile stderr'e yazdigi icin bu kalip guvenilmez.
  Cozum: stderr'i dosyaya yonlendirmek ve cagri boyunca 'Continue' kullanmak.
#>
function Invoke-Native {
    param([Parameter(Mandatory)][string]$File, [string[]]$Arguments = @())
    $errFile = [IO.Path]::GetTempFileName()
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out  = & $File @Arguments 2>$errFile | Out-String
        $code = $LASTEXITCODE
        $err  = if (Test-Path $errFile) { Get-Content $errFile -Raw } else { '' }
        [pscustomobject]@{ ExitCode = $code; Output = $out; Error = $err }
    } catch {
        [pscustomobject]@{ ExitCode = -1; Output = ''; Error = $_.Exception.Message }
    } finally {
        $ErrorActionPreference = $prev
        Remove-Item $errFile -ErrorAction SilentlyContinue
    }
}

# Ciktisi kullaniciya gorunmesi gereken uzun islemler icin (derleme vb.)
function Invoke-NativeLive {
    param([Parameter(Mandatory)][string]$File, [string[]]$Arguments = @())
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $File @Arguments; return $LASTEXITCODE }
    catch { Write-Host "  $($_.Exception.Message)"; return -1 }
    finally { $ErrorActionPreference = $prev }
}

<#
  Kaydedilmis bir imaj, uretildigi arac yuzunden onekli gelebilir
  (or. podman "localhost/betodds:latest" yazar). docker-compose ise
  "betodds:latest" arar; eslesmezse yeniden derlemeye kalkar.
  Yukleme sonrasi beklenen ada etiketliyoruz.
#>
function Set-ExpectedTag {
    param([Parameter(Mandatory)][string]$Wanted)
    if ((Invoke-Native docker @('image', 'inspect', $Wanted)).ExitCode -eq 0) { return $true }
    $r = Invoke-Native docker @('images', '--format', '{{.Repository}}:{{.Tag}}')
    $match = $r.Output -split "`n" |
             ForEach-Object { $_.Trim() } |
             Where-Object { $_ -and ($_ -replace '^.*/', '') -eq $Wanted } |
             Select-Object -First 1
    if ($match) {
        Say "  $match -> $Wanted olarak etiketleniyor"
        return ((Invoke-Native docker @('tag', $match, $Wanted)).ExitCode -eq 0)
    }
    return $false
}

function Test-DockerReady { (Invoke-Native docker @('info')).ExitCode -eq 0 }

# Yerel yolda DPI proxy'si de bize ait: byedpi'nin Windows surumunu indirip
# calistiriyoruz. (Docker yolunda proxy zaten yiginin icinde bir servis.)
$BYEDPI_URL = 'https://github.com/hufrea/byedpi/releases/download/v0.17.3/byedpi-17.3-x86_64-w64.zip'

# Windows'a ozel bir cmdlet yerine tasinabilir soket testi kullaniyoruz:
# cmdlet yoksa -ErrorAction kurtarmaz, ayrica "dinleyen soket" ile
# "baglanti kabul eden soket" ayni sey degildir.
<#
  Windows'ta "python" komutu, Microsoft Store'un App Execution Alias sahtesi
  olabilir: calistirilinca Store'u acar, kod calistirmaz. Bu yuzden komutun
  VAR OLMASI yetmez - gercekten kod calistirdigini dogruluyoruz.
  Sirasiyla python, python3 ve py -3 deneniyor.
#>
function Find-Python {
    foreach ($cand in @(@('python', @()), @('python3', @()), @('py', @('-3')))) {
        $exe = $cand[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $r = Invoke-Native $exe ($cand[1] + @('-c', 'import sys; print(sys.version_info[0], sys.version_info[1])'))
        if ($r.ExitCode -eq 0 -and $r.Output -match '^\s*(\d+)\s+(\d+)') {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -eq 3 -and $min -ge 10) {
                return [pscustomobject]@{ Exe = $exe; Prefix = $cand[1]; Version = "$maj.$min" }
            }
            Say "  $exe bulundu ama surumu eski: $maj.$min (3.10+ gerekli)"
        }
    }
    return $null
}

function Test-PortOpen {
    param([int]$Port, [int]$TimeoutMs = 800)
    try {
        $c = New-Object Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs)
        if ($ok) { $c.EndConnect($iar) }
        $c.Close()
        return $ok
    } catch { return $false }
}

function Start-LocalProxy {
    param([string]$ProxyArgs = '-r 1+s')

    # Zaten 1080'i dinleyen bir sey varsa dokunma
    if (Test-PortOpen 1080) { Say '  Proxy zaten calisiyor (port 1080).'; return $true }

    $dir = Join-Path $PSScriptRoot 'tools\byedpi'
    $exe = Join-Path $dir 'ciadpi.exe'
    if (-not (Test-Path $exe)) {
        # Once PAKETTEKI kopya: tam paketle gelindiginde GitHub'a hic cikmayalim
        # (bu betigin indirdigi adres bircok agda zaten engelli).
        $local = Get-ChildItem (Join-Path $PSScriptRoot 'vendor\byedpi-win') `
                 -Filter '*.zip' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($local) {
            Say '  DPI bypass proxy''si paketten aciliyor...'
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            Expand-Archive -Path $local.FullName -DestinationPath $dir -Force
        }
    }
    if (-not (Test-Path $exe)) {
        Say '  DPI bypass proxy''si (byedpi) indiriliyor...'
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $zip = Join-Path $dir 'byedpi.zip'
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $BYEDPI_URL -OutFile $zip -UseBasicParsing -TimeoutSec 90
            Expand-Archive -Path $zip -DestinationPath $dir -Force
            Remove-Item $zip -ErrorAction SilentlyContinue
        } catch {
            Warn "byedpi indirilemedi: $($_.Exception.Message)"
            Warn 'Proxy olmadan devam ediliyor; site engelliyse veri gelmez.'
            return $false
        }
    }
    if (-not (Test-Path $exe)) { Warn 'ciadpi.exe bulunamadi.'; return $false }

    Start-Process -FilePath $exe `
        -ArgumentList (@('-i', '127.0.0.1', '-p', '1080') + $ProxyArgs.Split(' ')) `
        -WindowStyle Hidden
    Start-Sleep -Seconds 2
    $ok = Test-PortOpen 1080
    if ($ok) { Say '  Proxy calisiyor (127.0.0.1:1080).' }
    else { Warn 'Proxy baslatilamadi.' }
    return $ok
}

function Invoke-Winget {
    param([string]$Id, [string]$Label)
    if (-not (Have winget)) {
        Fail "winget bulunamadi. $Label paketini elle kurun ya da Microsoft Store'dan 'App Installer' yukleyin."
    }
    Say "  $Label kuruluyor (winget: $Id)..."
    $code = Invoke-NativeLive winget @('install', '--id', $Id, '--exact', '--silent',
                                       '--accept-package-agreements', '--accept-source-agreements')
    # 0 = kuruldu, -1978335189 = zaten kurulu
    if ($code -ne 0 -and $code -ne -1978335189) {
        Fail "$Label kurulamadi (winget cikis kodu $code)."
    }
    Update-PathFromRegistry
}

# Docker Desktop birden fazla konuma kurulabiliyor; ayrica Join-Path null
# bir kok ile cagrildiginda sonlandirici hata verir - her koku once suzuyoruz.
function Find-DockerDesktop {
    $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramW6432,
               $env:LOCALAPPDATA) | Where-Object { $_ }
    $subs  = @('Docker\Docker\Docker Desktop.exe',
               'Programs\Docker\Docker\Docker Desktop.exe')
    foreach ($r in $roots) {
        foreach ($sub in $subs) {
            $p = Join-Path $r $sub
            if (Test-Path $p) { return $p }
        }
    }
    return $null
}

function Wait-DockerEngine {
    param([int]$TimeoutSec = $(if ($env:BETODDS_DOCKER_WAIT) { [int]$env:BETODDS_DOCKER_WAIT } else { 180 }))
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) { return $true }
        Start-Sleep -Seconds 4
    }
    return $false
}

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  BetOdds - kurulum ve calistirma' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan

# ------------------------------------------------------------------ 1) kurulum
Head '[1/4] Gerekli yazilimlar'

$useDocker = $false

if (-not $Native) {
    if (Have docker) {
        Say '  docker bulundu.'
        $useDocker = $true
    } elseif ($SkipInstall) {
        Warn 'docker yok ve -SkipInstall verildi; yerel kuruluma geciliyor.'
    } else {
        if (-not (Test-Admin)) {
            Say '  Docker Desktop kurulumu yonetici yetkisi istiyor; yukseltiliyor...'
            # param() ile baglanan switch'ler $args icinde YOKTUR; elle tasiyoruz,
            # yoksa yukseltilmis oturum farkli modda calisirdi.
            $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass',
                         '-File', "`"$PSCommandPath`"")
            if ($Native)      { $argList += '-Native' }
            if ($SkipInstall) { $argList += '-SkipInstall' }
            Start-Process powershell -Verb RunAs -ArgumentList $argList
            exit 0
        }
        Invoke-Winget 'Docker.DockerDesktop' 'Docker Desktop'
        $useDocker = Have docker
        if (-not $useDocker) {
            Warn 'Docker kuruldu ama PATH''e dusmedi. Oturumu kapatip acin ve bu dosyayi tekrar calistirin.'
            Say ''
            Read-Host 'Enter ile cikin' | Out-Null
            exit 0
        }
    }
}

if ($useDocker) {
    if (-not (Test-DockerReady)) {
        $exe = Find-DockerDesktop
        if ($exe) {
            Say '  Docker Desktop baslatiliyor...'
            Start-Process $exe | Out-Null
        } else {
            Say '  Docker Desktop uygulamasi bulunamadi; motorun acilmasi bekleniyor...'
        }
        if (-not (Wait-DockerEngine)) {
            Fail @'
Docker motoru baslamadi.

Muhtemel sebepler:
  * Docker Desktop ilk kurulumdan sonra YENIDEN BASLATMA istiyor olabilir.
    Bilgisayari yeniden baslatip bu dosyayi tekrar calistirin.
  * WSL2 kurulu degilse yonetici PowerShell'de: wsl --install
  * Docker Desktop'i elle baslatip balina simgesi "running" olunca
    bu dosyayi tekrar calistirin.

"Virtualization support not detected" hatasi aliyorsaniz once teshis:
    powershell -ExecutionPolicy Bypass -File scripts\tani.ps1

Sanallastirma hic acilamiyorsa Docker'a gerek yok:
    KURULUM.bat -Native
'@
        }
    }
    $cv = Invoke-Native docker @('compose', 'version')
    if ($cv.ExitCode -ne 0) {
        Fail "docker compose bulunamadi. Docker Desktop'i guncelleyin.`n$($cv.Error)"
    }
    Say '  Docker motoru calisiyor.'
} else {
    $script:Py = Find-Python
    if (-not $Py -and -not $SkipInstall) {
        Invoke-Winget 'Python.Python.3.12' 'Python 3.12'
        $script:Py = Find-Python
    }
    if (-not $Py) {
        Fail @'
Calisan bir Python 3.10+ bulunamadi.

Kurulduysa: bu pencereyi kapatip yeni bir pencerede tekrar deneyin (PATH
guncellenmis olmali). Windows'ta "python" komutu Microsoft Store kisayolu
olabilir; python.org'dan kurup "Add python.exe to PATH" secenegini isaretleyin.
'@
    }
    Say "  Python $($Py.Version) bulundu ($($Py.Exe))."

    # node YALNIZCA arayuz derlemek icin degil: backend de sezon tablolarini
    # ayristirmak icin kullaniyor. Hazir dist olsa bile kuruyoruz.
    if (-not (Have node) -and -not $SkipInstall) {
        Invoke-Winget 'OpenJS.NodeJS.LTS' 'Node.js LTS'
    }
}

# ------------------------------------------------------------------ 2) ag
Head '[2/4] Ag ayarlari'
New-Item -ItemType Directory -Force -Path 'data' | Out-Null
if (Test-Path 'backend/env') {
    Say '  backend/env zaten var, dokunulmadi.'
    Say '  (yeniden tespit icin bu dosyayi silip tekrar calistirin)'
} else {
    & (Join-Path $PSScriptRoot 'scripts/detect-network.ps1')
}

# ------------------------------------------------------------------ 3) derle
Head '[3/4] Derleme'

$script:loaded = $false
if ($useDocker) {
    # Onceden kaydedilmis imajlar varsa internetten derlemek yerine onlari yukle
    # (byedpi GitHub'dan klonlaniyor; erisim yoksa bu yol kullanilir).
    if (Test-Path 'images') {
        $tars = Get-ChildItem 'images' -File |
                Where-Object { $_.Name -match '\.tar(\.gz)?$' }
        foreach ($t in $tars) {
            Say "  $($t.Name) yukleniyor ($([math]::Round($t.Length/1MB)) MB)..."
            Invoke-NativeLive docker @('load', '-i', $t.FullName) | Out-Null
        }
        if ($tars) {
            $ok1 = Set-ExpectedTag 'betodds:latest'
            $ok2 = Set-ExpectedTag 'betodds-proxy:latest'
            $loaded = ($ok1 -and $ok2)
            if ($loaded) { Say '  Hazir imajlar yuklendi; derleme atlaniyor.' }
            else { Warn 'Imajlar eksik yuklendi; derlemeye gecilecek.' }
        }
    }
    if (-not $loaded) {
        Say '  Imajlar derleniyor (ilk seferde birkac dakika surer)...'
        if ((Invoke-NativeLive docker @('compose', 'build')) -ne 0) {
            Fail @'
Imaj derlenemedi.

Derleme su adreslere erisim ister (GitHub'a ARTIK GEREK YOK - byedpi kaynagi
vendor\byedpi altinda gomulu geliyor):
  * dl-cdn.alpinelinux.org  (proxy imaji)
  * pypi.org                (Python bagimliliklari)
  * registry.npmjs.org      (arayuz derlemesi)

Bunlar da engelliyse imajlari erisimi olan bir makinede uretip tasiyin:

  docker save betodds:latest       -o images\betodds.tar
  docker save betodds-proxy:latest -o images\betodds-proxy.tar

Dosyalari proje icindeki images\ klasorune koyup bu dosyayi tekrar calistirin;
script derlemek yerine onlari yukler.
'@
        }
    }
} else {
    if (-not (Test-Path 'backend/.venv')) {
        Say '  Sanal ortam olusturuluyor...'
        if ((Invoke-NativeLive $Py.Exe ($Py.Prefix + @('-m', 'venv', 'backend/.venv'))) -ne 0) {
            Fail 'venv olusturulamadi'
        }
    }
    $py = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { Fail "sanal ortam bozuk: $py yok" }
    Say '  Python bagimliliklari kuruluyor...'
    Invoke-NativeLive $py @('-m', 'pip', 'install', '--quiet', '--upgrade', 'pip') | Out-Null
    if ((Invoke-NativeLive $py @('-m', 'pip', 'install', '--quiet', '-r',
                                 'backend/requirements.txt')) -ne 0) {
        Fail 'bagimliliklar kurulamadi'
    }

    if (-not (Test-Path 'frontend/dist')) {
        if (-not (Have npm)) { Fail 'frontend/dist yok ve npm de yok.' }
        Say '  Arayuz derleniyor...'
        Push-Location frontend
        Invoke-NativeLive npm @('ci', '--no-audit', '--no-fund') | Out-Null
        Invoke-NativeLive npm @('run', 'build') | Out-Null
        Pop-Location
        if (-not (Test-Path 'frontend/dist')) { Fail 'arayuz derlenemedi' }
    } else {
        Say '  Hazir arayuz (frontend/dist) kullanilacak.'
    }
    if (-not (Have node)) {
        Warn 'node yok -> sezon tablosu cekimi calismaz; diger her sey normal calisir.'
    }
}

# ------------------------------------------------------------------ 4) calistir
Head '[4/4] Calistirma'

if ($useDocker) {
    # Imajlar hazir yuklendiyse --no-build: compose'un derlemeye kalkma
    # ihtimalini tamamen kaldirir (ag kapaliyken kritik).
    $upArgs = @('compose', 'up', '-d')
    if ($loaded) { $upArgs += '--no-build' }
    if ((Invoke-NativeLive docker $upArgs) -ne 0) {
        Fail 'servisler baslatilamadi'
    }
    Say '  Konteynerler baslatildi.'
} else {
    $envPath = 'backend/env'
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
                [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
            }
        }
    }
    Start-LocalProxy -ProxyArgs $ProxyArgs | Out-Null
    $py = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
    # Cikti dosyaya yazilsin: pencere kapanirsa hata izi kalmazdi.
    New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
    $outLog = Join-Path $PSScriptRoot 'logs\backend.log'
    $errLog = Join-Path $PSScriptRoot 'logs\backend.err.log'
    $proc = Start-Process -FilePath $py `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
                        '--host', '127.0.0.1', '--port', '8000') `
        -WorkingDirectory $PSScriptRoot -WindowStyle Minimized -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    Say "  Sunucu baslatildi (PID $($proc.Id)); loglar: logs\backend.err.log"
    $script:BackendProc = $proc
}

Head 'Saglik kontrolu'
$health = $null
foreach ($i in 1..45) {
    Start-Sleep -Seconds 2
    try { $health = Invoke-RestMethod -Uri "$APP_URL/api/health" -TimeoutSec 3; break } catch { }
}

if (-not $health) {
    Warn 'Uygulama yanit vermedi.'
    if ($useDocker) {
        Invoke-NativeLive docker @('compose', 'logs', '--tail', '40') | Out-Null
    } else {
        if ($script:BackendProc -and $script:BackendProc.HasExited) {
            Warn "Sunucu sureci sonlandi (cikis kodu $($script:BackendProc.ExitCode))."
        }
        foreach ($f in @('logs\backend.err.log', 'logs\backend.log')) {
            if (Test-Path $f) {
                $tail = Get-Content $f -Tail 25 -ErrorAction SilentlyContinue
                if ($tail) {
                    Write-Host ''
                    Write-Host "  --- $f (son 25 satir) ---" -ForegroundColor Yellow
                    $tail | ForEach-Object { Write-Host "  $_" }
                }
            }
        }
    }
    Fail 'Baslatilamadi.'
}

Write-Host ''
Write-Host "  HAZIR ->  $APP_URL" -ForegroundColor Green
Write-Host ("  Veritabani: {0} mac, {1} mac-oncesi arsiv, {2} oran kaydi" -f `
    $health.db.matches, $health.db.snapshots, $health.db.ticks)

if ($health.collector.last_error) {
    Write-Host ''
    Warn 'Toplayici veri cekemiyor:'
    Write-Host ("    {0}" -f $health.collector.last_error)
    Write-Host ''
    Write-Host '    Proxy stratejisi tutmamis olabilir. docker-compose.yml icinde'
    Write-Host '    CIADPI_ARGS degerini "-q 1+s" ya da "-r 1+s" yapip:'
    Write-Host '      docker compose up -d --force-recreate proxy'
}

Start-Process $APP_URL | Out-Null

Write-Host ''
if ($useDocker) {
    # Kacirilan mac-oncesi oranlar GERI ALINAMAZ (site mac bitince siliyor),
    # bu yuzden toplayicinin yeniden baslatmalardan sonra da ayaga kalkmasi onemli.
    Write-Host '  ONEMLI - veri kaybini onlemek icin:' -ForegroundColor Yellow
    Write-Host '    Docker Desktop > Settings > General bolumunde'
    Write-Host '    "Start Docker Desktop when you sign in" secenegini ACIN.'
    Write-Host '    Konteynerler "restart: unless-stopped" ile isaretli; Docker'
    Write-Host '    acilinca kendiliginden baslarlar. Docker kapaliyken oynanan'
    Write-Host '    maclarin mac-oncesi oranlari kalici olarak kaybolur.'
    Write-Host ''
    Write-Host '  Durdur:  docker compose down'
    Write-Host '  Loglar:  docker compose logs -f betodds'
} else {
    Write-Host '  Durdurmak icin:'
    Write-Host '    Get-Process python, ciadpi -ErrorAction SilentlyContinue | Stop-Process'
}
Write-Host ''
Read-Host 'Enter ile bu pencereyi kapatin' | Out-Null
