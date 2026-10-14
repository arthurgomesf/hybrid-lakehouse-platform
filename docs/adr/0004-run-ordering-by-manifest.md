# ADR 0004: Ordem Entre Runs Pelo Horario Do Manifest

## Status

Aceita

## Contexto

O Bronze precisava decidir qual versao de um registro e a mais recente. A
primeira versao ordenava pelo `run_id` convertido em numero. Havia dois
formatos de `run_id` convivendo:

- execucoes da pipeline usam o numero do build (ex.: `420`);
- execucoes locais e o container de exportacao usam um timestamp
  (ex.: `20260924131533`).

Qualquer run local enviado para a landing passava a "vencer" todos os runs da
pipeline, independentemente de quando aconteceu. O dedup por
`_bronze_loaded_at` tambem nao servia: o valor e igual para todas as linhas
carregadas na mesma execucao.

## Decisao

- O manifest registra `started_at` (UTC) de cada run.
- Bronze e Silver ordenam versoes por `_run_started_at`, lido do manifest.
- O MERGE so atualiza quando `s._run_started_at > t._run_started_at`, entao
  reprocessar um run antigo nunca sobrescreve dado mais novo.
- `run_id` vira apenas identificador, nunca criterio de ordem.

## Consequencias

- qualquer orquestrador pode gerar `run_id` no formato que quiser;
- runs sem manifest (incompletos) nem entram na disputa;
- depende do relogio do agente estar correto (UTC sincronizado).
