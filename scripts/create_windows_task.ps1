# ATLAS B2G — Cria a tarefa agendada do Windows (toda segunda-feira, 08:00)
# Rode UMA vez. Pode pedir confirmacao de administrador.
$proj = Split-Path -Parent $PSScriptRoot
$ps1  = Join-Path $proj "scripts\run_atlas_weekly.ps1"
$nome = "ATLAS B2G Weekly"

$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ps1`"" -WorkingDirectory $proj
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 8:00am
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

try {
  Register-ScheduledTask -TaskName $nome -Action $action -Trigger $trigger -Settings $set `
    -Description "Rotina semanal de inteligencia comercial ATLAS B2G (PNCP, DF+GO, TI)" -Force | Out-Null
  Write-Output "OK: tarefa '$nome' criada — executa toda segunda-feira as 08:00."
  Write-Output "Testar agora:  Start-ScheduledTask -TaskName '$nome'"
  Write-Output "Remover:       Unregister-ScheduledTask -TaskName '$nome' -Confirm:`$false"
} catch {
  Write-Output "Falha via Register-ScheduledTask: $($_.Exception.Message)"
  Write-Output ""
  Write-Output "Alternativa (rode no Prompt como admin):"
  Write-Output "schtasks /Create /TN `"$nome`" /TR `"powershell -NoProfile -ExecutionPolicy Bypass -File '$ps1'`" /SC WEEKLY /D MON /ST 08:00 /F"
}
