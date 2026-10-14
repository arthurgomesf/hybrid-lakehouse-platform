# ADR 0001: Plataforma Analitica Hibrida

## Status

Aceita

## Contexto

A plataforma corporativa de dados sera usada para integrar fontes industriais e corporativas, incluindo Motan Gravimetrico, INJET e SAP.

O Microsoft Fabric sera a plataforma analitica corporativa, mas a capacidade disponivel deve ser usada com criterio. Algumas fontes, como o coletor OPC UA do Motan, geram dados de alta frequencia que possuem grande valor operacional e tecnico, mas nem sempre precisam ser replicados integralmente para o Fabric.

O sistema atual do Motan ja possui um armazenamento operacional on-premise em PostgreSQL/TimescaleDB, adequado para series temporais, troubleshooting, retencao tecnica e consultas detalhadas.

## Decisao

Adotaremos uma arquitetura hibrida:

- dados brutos industriais de alta frequencia podem permanecer em armazenamentos operacionais on-premise;
- o Fabric sera usado prioritariamente para dados analiticos curados, incrementais e relevantes para consumo corporativo;
- a camada Bronze no Fabric sera seletiva, e nao necessariamente uma copia completa de todo dado raw disponivel nas fontes;
- Data Contracts poderao documentar tanto fontes on-premise quanto datasets publicados no Fabric;
- Data Products deverao representar entregaveis analiticos de negocio, e nao simples dumps de sistemas de origem.

## Aplicacao Inicial

Para o onboarding inicial do Motan, SAP e INJET:

- o raw OPC UA detalhado do Motan permanece no TimescaleDB on-premise por padrao;
- o Fabric deve receber inicialmente dados agregados, contextuais ou consolidados por OP;
- SAP e INJET devem ser tratados como fontes independentes, com contratos proprios;
- o primeiro Data Product sera orientado ao controle de dosagem real vs planejado da manufatura.

Datasets candidatos ao Fabric nesta fase:

- janelas de OP do Motan;
- consumo real total por OP;
- consumo real por componente por OP;
- ordens de producao SAP;
- componentes planejados SAP;
- eventos relevantes de sincronizacao;
- comparacao entre dosado real e planejado SAP.

O raw completo de `opc_readings` nao sera replicado integralmente para o Fabric por padrao.

## Consequencias Positivas

- reduz consumo desnecessario de capacity no Fabric;
- preserva dados industriais detalhados em uma tecnologia apropriada para series temporais;
- separa armazenamento operacional de plataforma analitica;
- permite governanca por Data Contracts sem obrigar replicacao fisica completa;
- facilita evolucao incremental dos Data Products;
- melhora rastreabilidade das decisoes de modelagem.

## Trade-offs

- algumas investigacoes tecnicas continuarao dependendo do acesso ao armazenamento on-premise;
- reprocessamentos analiticos completos podem exigir leitura do TimescaleDB;
- sera necessario definir criterios claros para quais dados entram no Fabric;
- pipelines deverao ser desenhadas para ingestao incremental e seletiva.

## Regras Orientadoras

- se o dado serve principalmente para debug tecnico de alta frequencia, ele pode permanecer on-premise;
- se o dado serve para decisao de producao, qualidade, custo, gestao ou consumo corporativo, ele e candidato ao Fabric;
- se um dataset cru tem alto volume e baixo valor analitico direto, ele nao deve ser replicado integralmente por padrao;
- contratos de fonte nao significam automaticamente tabelas no Fabric;
- Data Products devem publicar outputs curados e documentados.

## Decisoes Futuras Relacionadas

- definir politica de retencao e compressao do TimescaleDB;
- definir frequencias de ingestao incremental para Fabric;
- definir padrao de nomes para Bronze, Silver e Gold;
- definir criterio de promocao de um dataset on-premise para Fabric;
- definir SLAs e regras de qualidade por fonte e por Data Product.
