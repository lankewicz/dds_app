# Torre de Controle de execução dos DDS

O Firestore (`DDS`) permanece como registro oficial e fonte dos relatórios. O
monitor e os tablets usam projeções compactas no Firebase Storage:

```text
dados/chicoeletro/dds/controle/daily/AAAA-MM-DD.json.gz
dados/chicoeletro/dds/controle/monthly/AAAA-MM/EQUIPE.json.gz
```

A Function `onDdsProjectionSourceWritten` observa criações, alterações e
exclusões em `DDS/{submissionId}`. Ela marca a data como pendente e agenda uma
única tarefa `ddsProjectionBatch` para o próximo horário `:00` ou `:30`. Antes
das 07:00, a tarefa fica agendada para as 07:00. Sem documento novo, nenhuma
tarefa é criada e nenhum JSON é regravado.

O diário contém somente presença e campos de controle. O mensal é separado por
equipe e permite ao tablet restaurar seu cache sem consultar
`dds_training_exec`. Duplicidades são contabilizadas e sinalizadas no diário,
mas nunca removidas do Firestore.

## Implantação

1. Implantar as Functions: `firebase deploy --only functions`.
2. Garantir à conta executora da Function a permissão
   `roles/cloudtasks.enqueuer` para a fila `ddsProjectionBatch`.
3. Fazer o backfill antes de ativar o monitor/tablet novos:
   `npm run backfill:dds -- --start=AAAA-MM-DD --end=AAAA-MM-DD`.
4. Implantar `dds-webtools` com `DDS_PRESENCE_MODE=json`.
5. Distribuir o aplicativo Android atualizado.

O monitor mantém leitura temporária do antigo `_cache/days` quando o diário
novo ainda não existe. Esse fallback lê apenas Storage e não consulta `DDS`.
