# CV Generator - Azure Setup (from OmniFlow Central Pattern)

This script sets up the CV Generator for Azure Functions deployment, mirroring OmniFlow Central's proven infrastructure pattern.

## Quick Start

```powershell
# 1. Login to Azure
az login

# 2. Create resource group
az group create --name cv-generator-rg --location westeurope

# 3. Create storage account (must be globally unique)
az storage account create \
  --name cvgeneratorstore2025 \
  --resource-group cv-generator-rg \
  --location westeurope \
  --sku Standard_LRS

# 4. Get storage connection string
STORAGE_CONN=$(az storage account show-connection-string \
  --resource-group cv-generator-rg \
  --name cvgeneratorstore2025 \
  --query connectionString -o tsv)

echo "STORAGE_CONNECTION_STRING=$STORAGE_CONN"

# 5. Create blob containers
az storage container create \
  --name cv-themes \
  --account-name cvgeneratorstore2025

az storage container create \
  --name cv-templates \
  --account-name cvgeneratorstore2025

az storage container create \
  --name cv-fonts \
  --account-name cvgeneratorstore2025

# 6. Create function app (Flex Consumption)
az functionapp create \
  --resource-group cv-generator-rg \
  --consumption-plan-location westeurope \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name cv-generator \
  --storage-account cvgeneratorstore2025 \
  --sku FlexConsumption

# 7. Download publish profile
az functionapp deployment list-publishing-profiles \
  --resource-group cv-generator-rg \
  --name cv-generator \
  --output json > cv-generator-publish-profile.json

# 8. Extract XML from profile and add to GitHub secrets
# Go to: https://github.com/YOUR_REPO/settings/secrets/actions
# Add two secrets:
#   - AZURE_FUNCTIONAPP_PUBLISH_PROFILE: (paste XML from publish profile)
#   - STORAGE_CONNECTION_STRING: (paste connection string from step 4)

# 9. Upload initial theme/template files
az storage blob upload-batch \
  --account-name cvgeneratorstore2025 \
  --destination cv-themes \
  --source templates/themes \
  --overwrite

az storage blob upload-batch \
  --account-name cvgeneratorstore2025 \
  --destination cv-templates \
  --source templates/html \
  --overwrite

# 10. Configure function app settings
az functionapp config appsettings set \
  --name cv-generator \
  --resource-group cv-generator-rg \
  --settings \
    STORAGE_ACCOUNT_URL="https://cvgeneratorstore2025.blob.core.windows.net" \
    AZURE_BLOB_CONTAINER_THEMES="cv-themes" \
    AZURE_BLOB_CONTAINER_TEMPLATES="cv-templates" \
    AZURE_BLOB_CONTAINER_FONTS="cv-fonts" \
    CV_DEFAULT_THEME="zurich" \
    PLAYWRIGHT_BROWSERS_PATH="/home/site/wwwroot/.playwright" \
    AZURE_SDK_LOG_LEVEL="WARNING"

# 11. Trigger deployment via GitHub
git add .
git commit -m "setup: azure deployment configuration from omniflow pattern"
git push origin main

# GitHub Actions will:
# - Run tests (npm test)
# - Build Python package
# - Deploy to Azure Functions
# - Upload themes/templates to Blob Storage
```

## What Got Copied from OmniFlow Central

| File | Purpose | Adapted For |
|------|---------|------------|
| `host.json` | Azure Functions runtime config | CV Generator (Python 3.11, 10min timeout) |
| `local.settings.json` | Dev environment settings | CV themes/templates containers |
| `.funcignore` | Deployment exclusions | __pycache__, .venv, .git |
| `.github/workflows/deploy-azure.yml` | CI/CD pipeline | CV Generator (test + deploy + blob upload) |

## Expected Resources After Setup

- **Resource Group**: `cv-generator-rg`
- **Storage Account**: `cvgeneratorstore2025`
  - Containers: `cv-themes`, `cv-templates`, `cv-fonts`
- **Function App**: `cv-generator` (FlexConsumption, Python 3.11)
- **Application Insights**: Auto-created

## GitHub Secrets Required

1. `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` - XML from Azure Portal
2. `STORAGE_CONNECTION_STRING` - From Storage Account access keys

## Deployment Workflow

```
Local Git Push → GitHub Actions Trigger
  ↓
Test Job (pytest)
  ↓
Build-and-Deploy Job
  ├─ Install dependencies
  ├─ Deploy Function App
  └─ Upload Blob Storage artifacts
  ↓
Live at: https://cv-generator.azurewebsites.net/api/generate-cv
```

## Verification

```bash
# Check deployment status
az functionapp deployment list \
  --resource-group cv-generator-rg \
  --name cv-generator \
  --query "[].[deploymentId,status,received_time]" -o table

# Tail live logs
az functionapp log tail \
  --resource-group cv-generator-rg \
  --name cv-generator

# Test endpoint
curl -X POST https://cv-generator.azurewebsites.net/api/generate-cv \
  -H "Content-Type: application/json" \
  -d '{"cv_data":{"full_name":"Test"},"theme":"zurich"}'
```

## Notes

- **Cost**: ~$2–30/month on FlexConsumption depending on usage
- **Scale**: Auto-scales to meet demand
- **Monitoring**: Application Insights auto-enabled
- **Pattern**: Identical to OmniFlow Central for consistency
