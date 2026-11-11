# CertiTrack 360 - demostracion remota temporal.
#
# Levanta la aplicacion en este equipo con una base de datos de demostracion separada y la publica en internet
# con un tunel rapido de Cloudflare (HTTPS, sin cuenta ni abrir puertos del router). La direccion cambia en
# cada arranque y deja de funcionar al cerrar esta ventana (Ctrl+C) o apagar el equipo.
#
# Uso (desde la raiz del proyecto):
#   powershell -ExecutionPolicy Bypass -File scripts\demo_remota.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\demo_remota.ps1 -Reiniciar          # datos de demo desde cero
#   powershell -ExecutionPolicy Bypass -File scripts\demo_remota.ps1 -Clave "MiClave-2026" # clave fija
#
# Requisito: cloudflared  ->  winget install --id Cloudflare.cloudflared
# Solo datos simulados (seed_demo): nunca exponer asi datos reales.

param(
    [switch]$Reiniciar,
    [string]$Clave = "",
    [int]$Puerto = 8000
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No se encontro el entorno virtual (.venv). Creelo e instale requirements.txt." }

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $candidato = Join-Path ${env:ProgramFiles(x86)} "cloudflared\cloudflared.exe"
    if (Test-Path $candidato) { $cloudflared = $candidato }
}
if (-not $cloudflared) { throw "Falta cloudflared. Instalelo con: winget install --id Cloudflare.cloudflared" }

# Todo lo de la demo vive en demo_remota\ (ignorada por git): no toca db.sqlite3 ni media\ de desarrollo.
$carpeta = Join-Path $raiz "demo_remota"
New-Item -ItemType Directory -Force $carpeta | Out-Null

# Estas variables tienen prioridad sobre el archivo .env (settings.py solo completa las que falten).
$env:DJANGO_DEBUG = "0"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1,.trycloudflare.com"
$env:DJANGO_BEHIND_PROXY = "1"
$env:DJANGO_COOKIE_SECURE = "1"
$env:DATABASE_URL = "sqlite:///demo_remota/demo.sqlite3"
$env:MEDIA_ROOT = Join-Path $carpeta "media"
$env:DJANGO_SECRET_KEY = [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }))
$env:PYTHONIOENCODING = "utf-8"

Write-Host "Preparando la base de datos de demostracion..."
& $python manage.py migrate --noinput | Out-Null
if ($Reiniciar) { & $python manage.py seed_demo --reset } else { & $python manage.py seed_demo }
if ($LASTEXITCODE -ne 0) { throw "Fallo seed_demo." }

# La clave de seed_demo esta publicada en el repositorio: se reemplaza por una nueva en cada arranque.
if (-not $Clave) {
    $letras = "abcdefghjkmnpqrstuvwxyz23456789"
    $Clave = "Demo-" + (-join (1..4 | ForEach-Object { $letras[(Get-Random -Maximum $letras.Length)] })) + "-" +
             (-join (1..4 | ForEach-Object { $letras[(Get-Random -Maximum $letras.Length)] }))
}
$env:CERTITRACK_CLAVE_DEMO = $Clave
& $python manage.py shell -c "import os; from apps.cuentas.models import Usuario; [ (u.set_password(os.environ['CERTITRACK_CLAVE_DEMO']), u.save()) for u in Usuario.objects.all() ]"
Remove-Item Env:CERTITRACK_CLAVE_DEMO
if ($LASTEXITCODE -ne 0) { throw "No se pudo fijar la clave de los usuarios." }

$logServidor = Join-Path $carpeta "servidor.log"
$logTunel = Join-Path $carpeta "tunel.log"
Remove-Item $logTunel -ErrorAction SilentlyContinue

# --insecure: con DEBUG=0 el servidor de desarrollo no sirve /static/ sin esta opcion (no hay WhiteNoise).
$servidor = Start-Process $python -ArgumentList "manage.py", "runserver", "127.0.0.1:$Puerto", "--insecure", "--noreload" `
    -RedirectStandardOutput $logServidor -RedirectStandardError "$logServidor.err" -WindowStyle Hidden -PassThru
$tunel = Start-Process $cloudflared -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Puerto" `
    -RedirectStandardOutput "$logTunel.out" -RedirectStandardError $logTunel -WindowStyle Hidden -PassThru

try {
    Write-Host "Abriendo el tunel de Cloudflare..."
    $url = $null
    for ($i = 0; $i -lt 60 -and -not $url; $i++) {
        Start-Sleep -Seconds 1
        if ($servidor.HasExited) { throw "El servidor se detuvo. Revise $logServidor.err" }
        if ($tunel.HasExited) { throw "cloudflared se detuvo. Revise $logTunel" }
        if (Test-Path $logTunel) {
            $m = Select-String -Path $logTunel -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value }
        }
    }
    if (-not $url) { throw "No se obtuvo la direccion publica en 60 s. Revise $logTunel" }

    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host " CertiTrack 360 disponible en:  $url" -ForegroundColor Green
    Write-Host " Clave (todos los usuarios):    $Clave" -ForegroundColor Green
    Write-Host " Usuarios: gerente_demo, senior1, senior2, junior1, junior2, junior3, admin_demo"
    Write-Host " (la direccion puede tardar unos segundos en responder la primera vez)"
    Write-Host " Ctrl+C para cerrar la demostracion."
    Write-Host "==================================================================" -ForegroundColor Green
    while (-not $servidor.HasExited -and -not $tunel.HasExited) { Start-Sleep -Seconds 2 }
    Write-Host "Se detuvo el servidor o el tunel; cerrando." -ForegroundColor Yellow
}
finally {
    foreach ($p in @($tunel, $servidor)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
    Write-Host "Demostracion cerrada: la direccion publica ya no funciona."
}
