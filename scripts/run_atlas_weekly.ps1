# ATLAS B2G — Execucao da rotina semanal
# Roda a esteira completa e salva log. Abre a pasta de saida se for execucao manual.
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot          # pasta do projeto (pai de scripts/)
Set-Location $proj

$stamp  = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logdir = Join-Path $proj "logs"
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory $logdir | Out-Null }
$log = Join-Path $logdir "run_$stamp.log"

# localizar Python
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Error "Python nao encontrado no PATH. Instale o Python 3.x."; exit 1 }

"ATLAS B2G - iniciando rodada ($stamp)" | Tee-Object -FilePath $log
& $py "src\atlas_weekly_runner.py" "--config" "config\atlas_config.json" 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE

$today = Get-Date -Format "yyyy-MM-dd"
$out   = Join-Path $proj "outputs\rodadas\$today"
"Saida da rodada: $out (exit=$code)" | Tee-Object -FilePath $log -Append

# Abrir a pasta apenas em execucao manual (nao no agendador)
if ([Environment]::UserInteractive -and -not $env:ATLAS_NONINTERACTIVE) {
  try { if (Test-Path $out) { Invoke-Item $out } } catch {}
}
exit $code
