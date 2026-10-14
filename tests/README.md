# Tests

```bash
pytest -q
```

- `test_exporter.py`: unidade do exportador (render de SQL, schema do contrato,
  drift, layout da landing).
- `test_end_to_end.py`: gera as fontes ficticias, exporta dois runs, carrega
  Bronze/Silver/Gold e verifica cada caso de borda plantado pelo gerador
  (cancelamento, edicao antiga, CSRF vazio, codigo de retencao nao mapeado,
  BaseType errado, idempotencia e paridade do Gold com a view on-prem).
