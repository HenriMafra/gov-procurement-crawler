# ATLAS B2G — Operação Semanal (com o Painel)

Rotina da coordenação/operador, **toda segunda-feira**, usando o Painel Administrativo.

## Passo a passo (pelo painel)
1. Abrir o painel (`scripts\run_admin_panel.ps1`) e logar.
2. **Home** → conferir status da última rodada e do banco.
3. **Operação** → **Rodar produção agora** (Admin, confirma) — ou **Rodar produção + banco** se o banco estiver configurado.
4. Acompanhar o status; ao terminar, ver oportunidades/críticas/valor e abrir os arquivos.
5. **Arquivos Gerados** → abrir **Excel** (Top 10 / Lista de Ataque), **Relatório**, **Protótipo**, **ZIP**.
6. **Rodadas** → conferir comparativo com a rodada anterior (novas/alteradas/removidas).
7. Distribuir o **Top 10** e o **Mapa de Distribuição** aos responsáveis.
8. **Banco de Dados** → confirmar que a rodada foi carregada (se usar banco).
9. **Auditoria** → conferir o registro das execuções.
10. Ajustar **Configurações** (concorrentes/responsáveis/score) conforme feedback — com backup automático.

## Sem o painel (linha de comando / agendado)
- Agendado: tarefa do Windows (segundas 08:00) via `scripts\create_windows_task.ps1`.
- Manual: `python src\atlas_weekly_runner.py --config config\atlas_config_producao.json --tag PRODUCAO --write-db`

## Validação humana antes de abordar
- Confirmar **concorrentes** reais (config) · revisar itens **“necessita revisão”** · checar **renovação/aditivo** dos contratos vencidos no link do PNCP.

## O que enviar ao comercial
O **pacote ZIP** da rodada (Excel + relatório + protótipo + CSV de vendedores + resumo), ou o link do painel online (Fase 2).
