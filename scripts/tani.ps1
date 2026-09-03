<#
  "Virtualization support not detected" teshisi.

  Docker Desktop donanim sanallastirma ister. Bu betik neyin eksik oldugunu
  bulur ve tam olarak ne yapilacagini yazar.

  Kullanim:  powershell -ExecutionPolicy Bypass -File scripts\tani.ps1
#>
$ErrorActionPreference = 'Continue'
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Line { param($k, $v, $good = $null)
    $color = if ($good -eq $true) { 'Green' } elseif ($good -eq $false) { 'Red' } else { 'Gray' }
    Write-Host ("  {0,-38} " -f $k) -NoNewline
    Write-Host $v -ForegroundColor $color
}

Write-Host ''
Write-Host '=== Sanallastirma teshisi ===' -ForegroundColor Cyan
Write-Host ''

$fixes = @()

# --- CPU / BIOS ----------------------------------------------------------
try {
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $cs  = Get-CimInstance Win32_ComputerSystem
    Line 'Islemci' $cpu.Name
    Line 'BIOS sanallastirma (VT-x/AMD-V)' `
        $(if ($cpu.VirtualizationFirmwareEnabled) { 'ACIK' } else { 'KAPALI' }) `
        $cpu.VirtualizationFirmwareEnabled
    Line 'SLAT (EPT/NPT)' `
        $(if ($cpu.SecondLevelAddressTranslationExtensions) { 'var' } else { 'YOK' }) `
        $cpu.SecondLevelAddressTranslationExtensions
    Line 'Calisan hipervizor' `
        $(if ($cs.HypervisorPresent) { 'var' } else { 'yok' })
    Line 'Uretici / model' ("{0} / {1}" -f $cs.Manufacturer, $cs.Model)

    if ($cs.Model -match 'Virtual|VMware|VirtualBox|KVM|Hyper-V') {
        Write-Host ''
        Write-Host '  NOT: Bu makine bir sanal makine gibi gorunuyor.' -ForegroundColor Yellow
        Write-Host '       Ic ice sanallastirma (nested virtualization) acik degilse' -ForegroundColor Yellow
        Write-Host '       Docker Desktop calismaz.' -ForegroundColor Yellow
    }
    if (-not $cpu.VirtualizationFirmwareEnabled -and -not $cs.HypervisorPresent) {
        $fixes += @'
1) BIOS/UEFI'de sanallastirmayi acin  [EN OLASI SEBEP]
   Yeniden baslatirken kurulum tusuna basin (genelde F2/F10/Del/Esc).
   Ayarin adi uretici uretici degisir:
     Intel : "Intel (VMX) Virtualization Technology" / "Intel VT-x"
     AMD   : "SVM Mode" / "AMD-V"
   Genelde Advanced > CPU Configuration altindadir. Enabled yapip kaydedin.
   Kontrol: Gorev Yoneticisi > Performans > CPU > "Sanallastirma: Etkin"
'@
    }
} catch {
    Line 'CPU bilgisi' "okunamadi: $($_.Exception.Message)" $false
}

# --- Windows bilesenleri -------------------------------------------------
Write-Host ''
$features = @{
    'VirtualMachinePlatform'          = 'Sanal Makine Platformu'
    'Microsoft-Windows-Subsystem-Linux' = 'WSL'
    'Microsoft-Hyper-V-All'           = 'Hyper-V (istege bagli)'
}
$missing = @()
foreach ($f in $features.Keys) {
    try {
        $st = (Get-WindowsOptionalFeature -Online -FeatureName $f -ErrorAction Stop).State
        $on = ($st -eq 'Enabled')
        Line $features[$f] $st $on
        if (-not $on -and $f -ne 'Microsoft-Hyper-V-All') { $missing += $f }
    } catch {
        Line $features[$f] 'sorgulanamadi (yonetici olarak calistirin)'
    }
}
if ($missing.Count -gt 0) {
    $cmds = ($missing | ForEach-Object {
        "   dism /online /enable-feature /featurename:$_ /all /norestart" }) -join "`n"
    $fixes += @"
2) Eksik Windows bilesenlerini acin (YONETICI komut istemi):
$cmds
   Ardindan bilgisayari yeniden baslatin.
"@
}

# --- WSL -----------------------------------------------------------------
Write-Host ''
$wsl = & wsl --status 2>&1 | Out-String
if ($LASTEXITCODE -eq 0 -and $wsl.Trim()) {
    Line 'WSL' 'kurulu' $true
    $wsl.Trim().Split("`n") | Select-Object -First 4 | ForEach-Object {
        Write-Host "      $($_.Trim())" -ForegroundColor DarkGray }
} else {
    Line 'WSL' 'kurulu degil / yanit yok' $false
    $fixes += @'
3) WSL2 kurun (YONETICI PowerShell):
   wsl --install
   wsl --update
   Ardindan bilgisayari yeniden baslatin.
'@
}

# --- hipervizor acilis ayari --------------------------------------------
$bcd = & bcdedit /enum "{current}" 2>&1 | Out-String
if ($bcd -match 'hypervisorlaunchtype\s+(\w+)') {
    $val = $Matches[1]
    Line 'hypervisorlaunchtype' $val ($val -ne 'Off')
    if ($val -eq 'Off') {
        $fixes += @'
4) Hipervizor acilista kapatilmis (YONETICI komut istemi):
   bcdedit /set hypervisorlaunchtype auto
   Ardindan yeniden baslatin.
'@
    }
}

# --- sonuc ---------------------------------------------------------------
Write-Host ''
if ($fixes.Count -eq 0) {
    Write-Host 'Sanallastirma engeli gorunmuyor.' -ForegroundColor Green
    Write-Host 'Docker Desktop hala sikayet ediyorsa uygulamayi tamamen kapatip'
    Write-Host '(gorev cubugu simgesi > Quit) yeniden acin.'
} else {
    Write-Host '=== YAPILACAKLAR ===' -ForegroundColor Yellow
    foreach ($f in $fixes) { Write-Host ''; Write-Host $f }
}

Write-Host ''
Write-Host '--- Sanallastirma hic acilamiyorsa ---' -ForegroundColor Cyan
Write-Host '  Docker olmadan da calistirabilirsiniz (Python + Node dogrudan kurulur):'
Write-Host ''
Write-Host '    KURULUM.bat -Native' -ForegroundColor Green
Write-Host ''
Write-Host '  Bu yol sanallastirma gerektirmez; DPI proxy''si de otomatik indirilir.'
Write-Host ''
