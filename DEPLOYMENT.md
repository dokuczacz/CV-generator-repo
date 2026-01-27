# CV Generator - Production Deployment Guide

## Prerequisites

- Azure subscription with appropriate permissions
- Azure Functions Core Tools v4
- Azure CLI (`az`) installed and authenticated
- Python 3.11.9 (Functions runtime constraint: 3.7–3.12)

## Environment Variables (Production)

Required in Azure Functions App Settings:

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-...                    # Your OpenAI API key
OPENAI_PROMPT_ID=prompt_abc123...             # Your prompt ID for Responses API

# Azure Storage
AZURE_FUNCTIONS_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
CV_BLOB_STORE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net

# Feature Flags (Production Defaults)
CV_EXECUTION_LATCH=1                          # Enable PDF idempotency
CV_SINGLE_CALL_EXECUTION=1                    # Enforce single OpenAI call in execution
CV_DELTA_MODE=1                               # Enable delta context packs
CV_SESSION_TTL_HOURS=24                       # Session expiration (24h default)

# Optional: Logging & Monitoring
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=https://...
APPINSIGHTS_INSTRUMENTATIONKEY=...            # Application Insights key
```

## Deployment Steps

### 1. Prepare Azure Resources

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription <subscription-id>

# Create resource group (if not exists)
az group create --name cv-generator-rg --location westeurope

# Create storage account for blobs
az storage account create \
  --name cvgenstorage \
  --resource-group cv-generator-rg \
  --location westeurope \
  --sku Standard_LRS

# Create storage account for Azure Functions
az storage account create \
  --name cvgenfuncstorage \
  --resource-group cv-generator-rg \
  --location westeurope \
  --sku Standard_LRS

# Create Function App (Python 3.11, Linux)
az functionapp create \
  --resource-group cv-generator-rg \
  --consumption-plan-location westeurope \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name cv-generator-api \
  --storage-account cvgenfuncstorage \
  --os-type Linux
```

### 2. Configure App Settings

```bash
# Get storage connection strings
FUNC_STORAGE=$(az storage account show-connection-string \
  --name cvgenfuncstorage \
  --resource-group cv-generator-rg \
  --output tsv)

BLOB_STORAGE=$(az storage account show-connection-string \
  --name cvgenstorage \
  --resource-group cv-generator-rg \
  --output tsv)

# Set app settings
az functionapp config appsettings set \
  --name cv-generator-api \
  --resource-group cv-generator-rg \
  --settings \
    "AZURE_FUNCTIONS_STORAGE_CONNECTION_STRING=$FUNC_STORAGE" \
    "CV_BLOB_STORE_CONNECTION_STRING=$BLOB_STORAGE" \
    "OPENAI_API_KEY=<your-openai-api-key>" \
    "OPENAI_PROMPT_ID=<your-prompt-id>" \
    "CV_EXECUTION_LATCH=1" \
    "CV_SINGLE_CALL_EXECUTION=1" \
    "CV_DELTA_MODE=1" \
    "CV_SESSION_TTL_HOURS=24"
```

### 3. Deploy Function App

```bash
# From project root
cd "c:/AI memory/CV-generator-repo"

# Build and deploy
func azure functionapp publish cv-generator-api --python
```

### 4. Verify Deployment

Run smoke test against production endpoint:

```bash
# Update endpoint in smoke test
python tests/test_smoke_production.py --endpoint https://cv-generator-api.azurewebsites.net
```

## Post-Deployment Verification

1. **Health Check**
   ```bash
   curl https://cv-generator-api.azurewebsites.net/api/health
   # Expected: {"status": "healthy", "version": "1.0"}
   ```

2. **Monitor Application Insights**
   - Check function invocations
   - Monitor average response times (~10s expected)
   - Watch for `PDF_METRICS_SAMPLE` entries (10% sample rate)
   - Alert on `download_error` warnings in latch fallback path

3. **Verify Blob Storage**
   ```bash
   az storage container list \
     --account-name cvgenstorage \
     --connection-string "$BLOB_STORAGE"
   # Expected containers: cv-sessions, cv-pdfs, cv-photos
   ```

## Rollback Plan

If issues occur after deployment:

```bash
# Rollback to previous version
az functionapp deployment source config-zip \
  --resource-group cv-generator-rg \
  --name cv-generator-api \
  --src <previous-deployment-zip>
```

## Performance Benchmarks (Local)

Based on golden suite and stress testing:

| Metric | Value |
|--------|-------|
| First PDF generation | ~17s |
| Cached PDF (latch) | ~7-12s |
| Average response time | 10.56s |
| PDF size (2-page) | 110KB |
| Latch stability | 100% (5/5 identical) |
| Single-call enforcement | 100% (execution_mode=True) |

## Monitoring Checklist

- [ ] Application Insights configured
- [ ] Alert rules set for error rate >5%
- [ ] Alert rules set for avg response time >30s
- [ ] Blob storage metrics enabled
- [ ] Cost alerts configured (blob storage, function executions)
- [ ] Sampled metrics logging active (10% sample rate)

## Security Checklist

- [ ] OpenAI API key stored in Key Vault (optional, for enhanced security)
- [ ] Storage connection strings rotated every 90 days
- [ ] Function authentication enabled (API keys or Azure AD)
- [ ] CORS configured for allowed origins only
- [ ] Network restrictions applied (if needed)

## Troubleshooting

**Issue:** PDF generation times out (>60s)
- Check OpenAI API latency in logs
- Verify prompt ID is valid
- Check blob storage write performance

**Issue:** Latch returns 0-byte PDF
- Check for `download_error` warnings in logs
- Verify blob storage connection string
- Confirm `cv-pdfs` container exists and has read permissions

**Issue:** Session not found (404)
- Check session expiration (default 24h)
- Verify blob storage connection for session metadata
- Run cleanup tool to clear expired sessions

## Next Steps

1. Set up CI/CD pipeline (GitHub Actions or Azure DevOps)
2. Configure staging environment for pre-production testing
3. Implement blue-green deployment strategy
4. Set up automated daily smoke tests
