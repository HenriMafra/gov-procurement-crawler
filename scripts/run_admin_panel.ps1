# ATLAS B2G — Abre o Painel Administrativo (Streamlit) no navegador.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\run_admin_panel.ps1
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj

# Ambiente virtual, se existir
if (Test-Path ".venv\Scripts\Activate.ps1") { . .venv\Scripts\Activate.ps1 }

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Error "Python nao encontrado no PATH."; exit 1 }

# Garante dependencias do painel
& $py -m pip install --quiet streamlit bcrypt python-dotenv 2>$null

$logdir = Join-Path $proj "logs"
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory $logdir | Out-Null }

Write-Output "Abrindo ATLAS B2G - Painel Administrativo em http://localhost:8501 ..."
# Streamlit abre o navegador automaticamente; logs vao para logs\admin_panel.log
& $py -m streamlit run "admin_panel\app.py" --server.port 8501 2>&1 | Tee-Object -FilePath (Join-Path $logdir "admin_panel.log")
