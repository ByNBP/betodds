<#
  BetOdds - CEVRIMDISI KURULUM
  ============================
  Bu paket internet baglantisi olmadan kurulacak sekilde hazirlandi.
  Hicbir sey indirilmez; gereken her sey vendor\ ve images\ altinda gelir.

  Iki yol var, script uygun olani kendisi secer:

    A) Docker  : images\*.tar yuklenir, derleme yapilmaz.
                 Sart: Docker Desktop kurulu ve calisiyor olmali.
    B) Yerel   : vendor\python icindeki gomulu Python 3.12 acilir,
                 bagimliliklar vendor\wheels icinden kurulur.
                 Sart: YOK. Python, Node, Docker kurulu olmasi gerekmez.

  Kullanim:
    KURULUM-OFFLINE.bat            -> Docker varsa A, yoksa B
    KURULUM-OFFLINE.bat -Native    -> her halukarda B
    KURULUM-OFFLINE.bat -Port 8010 -> baska port
    KURULUM-OFFLINE.bat -NoProxy   -> DPI bypass proxy'sini baslatma (VPN modu)
#>
param(
    [switch]$Native,
    [switch]$NoProxy,
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Say  { param($m, $c = 'Gray') Write-Host $m -ForegroundColor $c }
function Head { param($m) Write-Host ''; Write-Host $m -ForegroundColor Cyan }
function Warn { param($m) Write-Host "  UYARI: $m" -ForegroundColor Yellow }
function Fail { param($m) Write-Host ''; Write-Host "HATA: $m" -ForegroundColor Red; exit 1 }
function Have { param($n) [bool](Get-Command $n -ErrorAction SilentlyContinue) }

function Invoke-Live {
    param([Parameter(Mandatory)][string]$File, [string[]]$Arguments = @())
    & $File @Arguments
    return $LASTEXITCODE
}

function Expand-Once {
    param([string]$Zip, [string]$Dest, [string]$Label)
    if (Test-Path $Dest) { Say "  $Label zaten acilmis."; return }
    if (-not (Test-Path $Zip)) { Fail "$Label paketi bulunamadi: $Zip" }
    Say "  $Label aciliyor..."
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $Dest -Force
}

Head 'BetOdds cevrimdisi kurulum'
Say  "  Klasor: $PSScriptRoot"

# --------------------------------------------------------------- A) Docker
$useDocker = $false
if (-not $Native) {
    if (Have docker) {
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) { $useDocker = $true }
        else { Warn 'Docker kurulu ama calismiyor; yerel kuruluma gecilecek.' }
    } else {
        Say '  Docker yok; yerel kurulum kullanilacak.'
    }
}

# Docker calisiyor olsa bile paket imajsiz uretilmis olabilir (yerel yol
# hicbir sey gerektirmediginden imajlari tasimak sart degil). Eskiden bu
# durumda kurulum HATA verip duruyordu; artik sessizce yerel yola gecer.
if ($useDocker) {
    $haveTars = @(Get-ChildItem 'images' -File -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -match '\.tar$' })
    if (-not $haveTars) {
        Say '  Pakette hazir imaj yok; yerel kurulum kullanilacak.'
        $useDocker = $false
    }
}

if ($useDocker) {
    Head '[1/2] Hazir imajlar yukleniyor'
    $tars = @(Get-ChildItem 'images' -File -ErrorAction SilentlyContinue |
              Where-Object { $_.Name -match '\.tar$' })
    if (-not $tars) { Fail 'images\*.tar bulunamadi. -Native ile yerel kurulumu deneyin.' }
    # 'docker load' ciktisi yuklenen imajin adini veriyor; etiketi ondan
    # kuruyoruz. DIKKAT: podman ile uretilen tar'lar "localhost/" onekli gelir
    # ve compose oneksiz adi bekliyor.
    $loaded = @()
    foreach ($t in $tars) {
        Say "  $($t.Name) ($([math]::Round($t.Length/1MB)) MB)..."
        $out = & docker load -i $t.FullName 2>&1
        if ($LASTEXITCODE -ne 0) {
            $out | ForEach-Object { Write-Host "    $_" }
            Fail "imaj yuklenemedi: $($t.Name)"
        }
        $loaded += ($out | Select-String -Pattern 'Loaded image(?:\(s\))?:\s*(.+)$' |
                    ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() })
    }

    # Etiketleme HER KURULUMDA yapilir. Onceden "betodds:latest zaten var mi"
    # diye bakiliyordu; ikinci kurulumda eski etiket duruyor oldugu icin yeni
    # yuklenen imaj etiketlenmiyor ve compose ESKI imaji baslatiyordu - Windows
    # tarafinda "proje eski haliyle goruntuleniyor" sikayetinin sebebi buydu.
    foreach ($want in @('betodds:latest', 'betodds-proxy:latest')) {
        $src = $loaded | Where-Object { ($_ -replace '^.*/', '') -eq $want } |
               Select-Object -First 1
        if (-not $src) {
            # tar icinde ad yoksa (eski docker surumu ciktiyi farkli basar)
            # imaj listesine duseriz.
            $all = (& docker images --format '{{.Repository}}:{{.Tag}}') -split "`n"
            $src = $all | ForEach-Object { $_.Trim() } |
                   Where-Object { $_ -and ($_ -replace '^.*/', '') -eq $want -and $_ -ne $want } |
                   Select-Object -First 1
        }
        if ($src -and $src -ne $want) { Say "  $src -> $want"; & docker tag $src $want }
        elseif (-not $src) {
            & docker image inspect $want *> $null
            if ($LASTEXITCODE -ne 0) { Fail "$want imaji yuklenemedi." }
        }
    }

    Head '[2/2] Calistiriliyor'
    # --force-recreate: onceki kurulumdan kalan konteyner eski imajla ayakta
    # olabilir; imaj degisse de compose onu oldugu gibi birakabiliyor.
    if ((Invoke-Live docker @('compose', 'up', '-d', '--no-build',
                              '--force-recreate')) -ne 0) {
        Fail 'docker compose baslatilamadi.'
    }
    Say '  Konteynerler ayakta.' 'Green'
    Write-Host ''
    Write-Host "  Arayuz : http://localhost:8000" -ForegroundColor Green
    Write-Host '  Loglar : docker compose logs -f betodds'
    Write-Host '  Durdur : docker compose down'
    Write-Host ''
    Write-Host '  VPN kullaniyorsan .env icindeki #BETODDS_PROXY= satirinin' -ForegroundColor Yellow
    Write-Host '  yorumunu kaldirip "docker compose up -d" komutunu tekrar calistir.' -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------- B) Yerel
Head '[1/4] Gomulu Python hazirlaniyor'

$runtime = Join-Path $PSScriptRoot 'runtime'
$pyDir   = Join-Path $runtime 'python'
$pyExe   = Join-Path $pyDir 'python.exe'

$pyZip = Get-ChildItem (Join-Path $PSScriptRoot 'vendor\python') -Filter '*embed-amd64.zip' `
         -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pyZip) { Fail 'vendor\python altinda gomulu Python zip''i yok.' }
Expand-Once $pyZip.FullName $pyDir 'Python 3.12'
if (-not (Test-Path $pyExe)) { Fail "python.exe bulunamadi: $pyExe" }

# Gomulu dagitim varsayilan olarak site-packages'i okumaz; ._pth dosyasindaki
# "import site" satirinin yorumunu kaldirmadan pip ile kurulan paketler
# gorunmez olur.
$pth = Get-ChildItem $pyDir -Filter 'python*._pth' | Select-Object -First 1
if ($pth) {
    $lines = Get-Content $pth.FullName
    if ($lines -match '^\s*#\s*import site') {
        ($lines -replace '^\s*#\s*import site', 'import site') |
            Set-Content $pth.FullName -Encoding ASCII
        Say '  site-packages etkinlestirildi.'
    }
    if (-not ($lines -match '^\s*Lib\\site-packages\s*$')) {
        Add-Content $pth.FullName 'Lib\site-packages' -Encoding ASCII
    }
}

Head '[2/4] Bagimliliklar kuruluyor (internet yok, wheel''lerden)'

$wheels = Join-Path $PSScriptRoot 'vendor\wheels'
if (-not (Test-Path $wheels)) { Fail 'vendor\wheels bulunamadi.' }

& $pyExe -c "import pip" *> $null
if ($LASTEXITCODE -ne 0) {
    $getpip = Join-Path $PSScriptRoot 'vendor\python\get-pip.py'
    if (-not (Test-Path $getpip)) { Fail 'vendor\python\get-pip.py yok.' }
    Say '  pip kuruluyor...'
    if ((Invoke-Live $pyExe @($getpip, '--no-index', '--find-links', $wheels, '--quiet')) -ne 0) {
        Fail 'pip kurulamadi.'
    }
}

$req = Join-Path $PSScriptRoot 'vendor\requirements-win.txt'
if (-not (Test-Path $req)) { $req = Join-Path $PSScriptRoot 'backend\requirements.txt' }
Say "  $((Split-Path $req -Leaf)) kuruluyor..."
if ((Invoke-Live $pyExe @('-m', 'pip', 'install', '--no-index',
                          '--find-links', $wheels, '-r', $req, '--quiet')) -ne 0) {
    Fail 'bagimliliklar kurulamadi.'
}
Say '  Tamam.' 'Green'

Head '[3/4] Yardimci araclar'

# Arayuz zaten derlenmis halde geliyor - npm/Node gerekmez.
if (Test-Path 'frontend\dist\index.html') { Say '  Arayuz hazir (frontend\dist).' }
else { Warn 'frontend\dist yok! Arayuz acilmaz, yalnizca /api calisir.' }

# Node yalnizca sezon puan durumu cekimi (backend\app\stats.py) icin gerekli.
$nodeZip = Get-ChildItem (Join-Path $PSScriptRoot 'vendor\node') -Filter '*.zip' `
           -ErrorAction SilentlyContinue | Select-Object -First 1
if ($nodeZip) {
    $nodeDir = Join-Path $runtime 'node'
    Expand-Once $nodeZip.FullName $nodeDir 'Node.js'
    $nodeBin = Get-ChildItem $nodeDir -Directory | Select-Object -First 1
    if ($nodeBin -and (Test-Path (Join-Path $nodeBin.FullName 'node.exe'))) {
        $env:PATH = "$($nodeBin.FullName);$env:PATH"
        Say '  node.exe PATH''e eklendi (sezon tablosu cekimi icin).'
    }
} else {
    Warn 'vendor\node yok -> sezon tablosu cekimi calismaz, digerleri normal calisir.'
}

# byedpi: DPI bypass proxy'si. VPN kullaniyorsan -NoProxy ile atlanabilir.
$dpiZip = Get-ChildItem (Join-Path $PSScriptRoot 'vendor\byedpi-win') -Filter '*.zip' `
          -ErrorAction SilentlyContinue | Select-Object -First 1
if ($dpiZip) {
    Expand-Once $dpiZip.FullName (Join-Path $PSScriptRoot 'tools\byedpi') 'byedpi'
}

Head '[4/4] Baslatiliyor'

# backend\env icindeki ayarlari surece yukle.
$envPath = Join-Path $PSScriptRoot 'backend\env'
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process')
        }
    }
}

function Test-Port {
    param([int]$Port)
    try {
        $c = New-Object Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(800)
        if ($ok) { $c.EndConnect($iar) }
        $c.Close()
        return $ok
    } catch { return $false }
}

# Yerel modda proxy konteyneri yok; paketten cikan ciadpi.exe'yi BIZ baslatiyoruz.
# Aksi halde eventsstat.com (sezon tablolari) SNI tabanli DPI'a takilir ve
# filtreli aglarda feed de gelmez.
$proxy = [Environment]::GetEnvironmentVariable('BETODDS_PROXY', 'Process')
if ($proxy -match '^socks5://(127\.0\.0\.1|localhost):(\d+)') {
    $p = [int]$Matches[2]

    if (-not $NoProxy -and -not (Test-Port $p)) {
        $dpiExe = Join-Path $PSScriptRoot 'tools\byedpi\ciadpi.exe'
        if (Test-Path $dpiExe) {
            # Strateji kok .env icindeki CIADPI_ARGS'tan; bu ag icin -r 1+s dogrulandi.
            $dpiArgs = '-r 1+s'
            $rootEnv = Join-Path $PSScriptRoot '.env'
            if (Test-Path $rootEnv) {
                $m = Select-String -Path $rootEnv -Pattern '^\s*CIADPI_ARGS\s*=\s*(.+)$' |
                     Select-Object -First 1
                if ($m) { $dpiArgs = $m.Matches[0].Groups[1].Value.Trim() }
            }
            Say "  DPI bypass proxy'si baslatiliyor (ciadpi $dpiArgs)..."
            Start-Process -FilePath $dpiExe `
                -ArgumentList "-i 127.0.0.1 -p $p $dpiArgs" `
                -WindowStyle Hidden | Out-Null
            for ($i = 0; $i -lt 10 -and -not (Test-Port $p); $i++) {
                Start-Sleep -Milliseconds 300
            }
            if (Test-Port $p) { Say "  proxy hazir: 127.0.0.1:$p" 'Green' }
        }
    }

    # Hala ayakta degilse (VPN modu ya da -NoProxy): ayari bosalt, yoksa httpx
    # baglanamayan bir socks5'e gider ve HICBIR istek cikmaz.
    if (-not (Test-Port $p)) {
        Warn "127.0.0.1:$p dinlenmiyor -> proxy devre disi birakildi (VPN modu)."
        [Environment]::SetEnvironmentVariable('BETODDS_PROXY', '', 'Process')
    }
}

$env:BETODDS_DATA   = Join-Path $PSScriptRoot 'data'
$env:BETODDS_STATIC = Join-Path $PSScriptRoot 'frontend\dist'
$env:PYTHONUNBUFFERED = '1'
New-Item -ItemType Directory -Force -Path $env:BETODDS_DATA | Out-Null

Write-Host ''
Write-Host "  Arayuz : http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host '  Durdur : bu pencerede Ctrl+C'
Write-Host '  Tekrar : BASLAT.bat'
Write-Host ''

& $pyExe -m uvicorn app.main:app --app-dir (Join-Path $PSScriptRoot 'backend') `
         --host 127.0.0.1 --port $Port
