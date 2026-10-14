# Infra

Definicoes reproduziveis da infraestrutura operacional, sem secrets:

- `agents/azure-devops/sap/`: agente Windows perto do SAP (script de registro);
- `agents/azure-devops/motan/`: agente Linux em container perto do chao de fabrica.

Storage, lakehouse e permissoes ainda sao criados manualmente; Infrastructure as
Code (Bicep ou Terraform) esta no backlog.
