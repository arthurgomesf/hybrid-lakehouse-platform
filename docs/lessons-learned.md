# Licoes Aprendidas

Problemas encontrados na primeira versao da plataforma (em ambiente real, com um
lakehouse de teste) e como esta versao resolve cada um. Os nomes de empresas,
servidores e dados foram trocados; os problemas sao reais.

## Dados

| Problema | Sintoma | Solucao nesta versao |
|---|---|---|
| Tipos inferidos do dado de cada run | uma coluna de imposto sem nenhum valor no run saiu com tipo `null`; quando o primeiro valor aparecesse, o Bronze (que le varios runs juntos) teria tipos em conflito | schema vem do contrato (`build_frame`); teste `test_csrf_keeps_decimal_type_when_all_null` |
| Watermark na data errada | extracao incremental por data de lancamento perdia edicoes e cancelamentos de documentos antigos | watermark por `UpdateDate`; cancelados extraidos com `is_cancelled` |
| Filtros por `LIKE` em nomes de imposto | `'%PIS%'`, `'%COFINS%'` e `'%CSRF%'` podiam somar um codigo combinado em varias colunas | mapeamento explicito codigo -> imposto (`tax_codes`) |
| Join sem tipo de documento | transferencias de outro tipo de documento com o mesmo numero eram ligadas ao pedido | filtro de `BaseType`; transferencias "isca" no gerador e teste dedicado |
| Placeholder em chave | documento sem CNPJ virava `'N/A'` e entrava em uma chave composta | `NULL` explicito |
| Data fixa no SQL | `>= '2026-01-01'` no meio da query; janela nao configuravel | parametro `:start_date` no `datasets.yaml` |
| Nomes de colunas diferentes por dataset | um dataset preservava `DocEntry`, outros saiam em snake_case, a config usava outro nome | snake_case em ingles desde o SQL, igual ao contrato |

## Carga No Lakehouse

| Problema | Sintoma | Solucao |
|---|---|---|
| Bronze relia toda a landing e sobrescrevia | custo crescente a cada execucao | so runs novos, via tabela `ctrl_ingested_runs` |
| "Versao mais recente" por `current_timestamp()` | todas as linhas de uma execucao tinham o mesmo valor; o dedup escolhia qualquer uma | ordem por `_run_started_at` do manifest |
| Ordem por `run_id` com dois formatos | run local (timestamp) vencia todos os runs da pipeline (numero do build) | [ADR 0004](adr/0004-run-ordering-by-manifest.md) |
| Run incompleto lido | manifest gravado no fim nao era consultado | Bronze so le runs com manifest |
| Silver rodava mesmo com Bronze falho | dependencia `Completed` na pipeline | `Succeeded` |
| Tabela de controle com "auto-correcao" | o controle recebia linhas duplicadas e um passo extra as removia | so grava quando algo novo entra |
| Gold copiado de uma view on-prem | a regra de negocio vivia fora da plataforma; tolerancia fixa no codigo | Gold calculado do Silver, tolerancia no contrato, teste de paridade com a view |
| Media de percentuais no relatorio | `AVERAGE(variance_percent)`: uma OP pequena pesava igual a uma grande | `DIVIDE(SUM(variance), SUM(planned))` |

## Operacao

| Problema | Licao |
|---|---|
| Agente de integracao em uma estacao de trabalho | quando a maquina desligava, o agendamento seguia enfileirando execucoes que eram canceladas depois de horas na fila. Agente de producao precisa de maquina sempre ligada |
| Dois agendadores para a mesma extracao (pipeline + container com loop) | execucoes concorrentes e `run_id` em formatos diferentes. Um unico orquestrador por fonte |
| Pipeline de transformacao agendada com a ingestao desligada | reprocessava o mesmo dado a cada hora, gastando capacidade. Agendar a transformacao depois da ingestao, nao em paralelo |
| Variavel secreta sem a marca de secreta na pipeline | o valor aparecia em claro para quem tinha acesso a definicao. Secret variables ou Key Vault, e rotacao quando houver duvida |
| Codigo do lakehouse fora do Git | sem historico nem revisao. Git Integration desde o primeiro notebook |
| Ambiente de teste com prazo | dados brutos fora do lakehouse (ADLS) e codigo no Git tornam a expiracao barata: tudo se reconstroi a partir da landing |

## Processo

- Contrato antes do codigo: grao, chave e tipos escritos antes da query evitam a
  maior parte dos problemas acima.
- Casos de borda viram dados de teste: cada bug encontrado ganhou um registro no
  gerador ficticio e um teste que falharia com o comportamento antigo.
- Um diagnostico honesto (o que existe x o que so esta documentado) vale mais que
  um diagrama bonito.
