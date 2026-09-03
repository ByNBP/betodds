<#
  Kurulum adimlarini atlar, yalnizca derleyip calistirir.

  Tum mantik KURULUM.ps1 icinde; burada ikinci bir kopya tutmuyoruz.
  (Onceki surumde ayni native-komut tuzagi iki dosyada birden vardi.)

  Kullanim:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
param([switch]$Native)

$root = Split-Path -Parent $PSScriptRoot
# DIKKAT: $args PowerShell'in otomatik degiskeni; uzerine yazmiyoruz.
$fwd = @('-SkipInstall')
if ($Native) { $fwd += '-Native' }
& (Join-Path $root 'KURULUM.ps1') @fwd
