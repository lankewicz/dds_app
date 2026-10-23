# Raspagem antiga desativada no Google Cloud

Em 09/10/2026, no projeto `dds-treinamentos`, região `us-central1`:

- `rotalog-sync`: escalonamento manual com zero instâncias. Verificado
  `manualInstanceCount: 0`; a URL retorna HTTP 503 enquanto desligada.
- Agenda `rotalog-daily-archive-0430`: estado `PAUSED`.
- Job `rotalog-daily-archive`: configuração preservada. A última execução
  listada já estava concluída; o job não mantém instâncias entre execuções.

Os recursos foram preservados para recuperação. A coleta é responsabilidade
do Orange Pi. O serviço do site `dds-admin-site` não foi alterado nesta ação.

## Recuperação, somente se necessária

```powershell
gcloud run services update rotalog-sync --scaling=auto --region=us-central1 --project=dds-treinamentos
gcloud scheduler jobs resume rotalog-daily-archive-0430 --location=us-central1 --project=dds-treinamentos
```

Não reativar estes recursos durante um deploy normal: isso pode duplicar a
coleta realizada pelo Orange Pi.
