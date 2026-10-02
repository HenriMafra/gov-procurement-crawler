# ATLAS B2G — Checklist de Operação Semanal

Rotina recomendada para a coordenação comercial (toda segunda-feira).

## Antes da reunião
- [ ] **1. Rodar a esteira** (ou conferir que a tarefa agendada rodou):
  `python src\atlas_weekly_runner.py --config config\atlas_config_producao.json --tag PRODUCAO`
- [ ] **2. Abrir o Excel** da rodada: `outputs\rodadas\PRODUCAO_AAAA-MM-DD\atlas_lista_ataque_comercial_AAAA-MM-DD.xlsx`
- [ ] **3. Conferir o Top 10 Semana** (aba) — alvos prioritários e valores.
- [ ] **4. Conferir "Comparativo Semanal"** — o que é **novo** vs a semana passada (foco do esforço).
- [ ] **5. Conferir "Revisão Manual"** — separar o que **não** deve ir para abordagem sem validação.
- [ ] **6. Validar concorrentes** — checar a aba "Por Concorrente"; confirmar/atualizar `concorrentes_conhecidos` no config.

## Na reunião / distribuição
- [ ] **7. Distribuir oportunidades** usando o **Mapa de Distribuição** (`mapa_distribuicao_comercial_*.md`) — por responsável/UF/categoria.
- [ ] **8. Atualizar responsáveis reais** (se a sugestão automática não bater) no config `responsaveis`.
- [ ] **9. Marcar como "em abordagem"** as que forem aceitas (anotar no Excel/planilha premium).
- [ ] **10. Confirmar renovação/aditivo** dos contratos **vencidos** antes de abordar (evita perseguir contrato já renovado).

## Envio e registro
- [ ] **11. Enviar o pacote** `atlas_pacote_producao_AAAA-MM-DD.zip` para o time (ou Excel + protótipo HTML).
- [ ] **12. Registrar feedback** dos vendedores (quais avançaram, quais eram inválidas).
- [ ] **13. Ajustar a configuração** para a próxima rodada (concorrentes confirmados, janelas, score mínimo, responsáveis).

## Pontos de atenção (validação humana)
- "Possível concorrente" = **a confirmar** (heurística/lista). Não tratar como certeza.
- "Necessita revisão" / baixa confiança = **validar o objeto** antes de abordar.
- Contrato **vencido** ≠ oportunidade garantida — pode já ter sido renovado/aditivado.
- Valores e datas vêm do PNCP — **conferir no link da fonte** antes de propostas formais.

## Indicadores para acompanhar semana a semana
- Nº de oportunidades / críticas · valor total mapeado.
- Novas vs removidas (Comparativo Semanal).
- Conversão: oportunidades que viraram abordagem / negociação / ganho.
