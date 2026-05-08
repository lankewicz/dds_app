# Script de Deploy para o Google Cloud Run (DDS Admin)
# Execute com: ./deploy.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Iniciando Deploy: DDS-Admin-Site       " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Executa o comando gcloud usando o arquivo de variáveis env.yaml
gcloud run deploy dds-admin-site `
  --source . `
  --region us-central1 `
  --project dds-treinamentos `
  --memory 1Gi `
  --timeout 900 `
  --clear-base-image `
  --env-vars-file env.yaml

# Verifica se o comando anterior foi bem sucedido
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[OK] Deploy concluído com sucesso!" -ForegroundColor Green
} else {
    Write-Host "`n[ERRO] Ocorreu uma falha durante o deploy. Verifique as mensagens acima." -ForegroundColor Red
    exit $LASTEXITCODE
}
