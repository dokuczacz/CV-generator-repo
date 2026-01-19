# CV Generator - OmniFlow Central Pattern Deployment

**Status**: ✅ Ready to deploy to Azure Functions

All configuration files have been copied from OmniFlow Central and adapted for CV Generator. You now have everything needed to go live.

---

## 🚀 Quick Start (3 Commands)

```powershell
# 1. Run setup script (creates all Azure resources)
.\setup-azure.ps1

# 2. Add GitHub secrets (copy-paste instructions from script output)
# Go to: https://github.com/YOUR_REPO/settings/secrets/actions

# 3. Push to main (triggers automatic deployment)
git push origin main
```

## Prerequisites

- Azure subscription with permissions to create resources
- Azure CLI (`az` command) installed
- GitHub repository with push access
- PowerShell 5.0+

---

## Step 1: Create Azure Resources (via Portal or Bicep)

### Option A: Using Azure Portal (Manual)

1. **Create Storage Account**
   - Name: `cvgeneratorstore` (must be globally unique)
   - Replication: LRS
   - Performance: Standard

2. **Create Blob Containers** (in the storage account)
   - `cv-themes`
   - `cv-templates`
   - `cv-fonts`

3. **Create Function App**
   - Name: `cv-generator`
   - Runtime: Python 3.11
   - Hosting: Flex Consumption (recommended for scale + cost)
   - Storage account: `cvgeneratorstore`

4. **Create Application Insights**
   - Name: `cv-generator-insights`
   - Link to Function App

### Option B: Using Bicep (Recommended for IaC)

```bash
cd infra
az group create --name cv-generator-rg --location westeurope
az deployment group create \
  --resource-group cv-generator-rg \
  --template-file main.bicep
```

---

## Step 2: Configure Azure Secrets in GitHub

Navigate to your GitHub repository → Settings → Secrets and Variables → Actions

Add these secrets:

### `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`

1. Azure Portal → Function Apps → cv-generator → Get publish profile
2. Copy entire XML content
3. Add as GitHub secret named `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`

### `STORAGE_CONNECTION_STRING`

1. Azure Portal → Storage Accounts → cvgeneratorstore → Access Keys
2. Copy "Connection string" for key1
3. Add as GitHub secret named `STORAGE_CONNECTION_STRING`

---

## Step 3: Configure Function App Settings

Navigate to Function App → Configuration → Application settings

Add these settings:

| Setting | Value | Notes |
|---------|-------|-------|
| `STORAGE_ACCOUNT_URL` | `https://cvgeneratorstore.blob.core.windows.net` | Replace with your storage account |
| `STORAGE_CONNECTION_STRING` | (from Access Keys) | Used by Python code |
| `STORAGE_CONTAINER_THEMES` | `cv-themes` | Must match blob container name |
| `STORAGE_CONTAINER_TEMPLATES` | `cv-templates` | Must match blob container name |
| `STORAGE_CONTAINER_FONTS` | `cv-fonts` | Must match blob container name |
| `PLAYWRIGHT_BROWSERS_PATH` | `/home/site/wwwroot/.playwright` | For Chromium cache |
| `CV_DEFAULT_THEME` | `zurich` | Default theme if not specified |
| `AZURE_SDK_LOG_LEVEL` | `WARNING` | Reduce noise in logs |

---

## Step 4: Upload Initial Theme & Template Files

Run locally (requires Azure CLI auth):

```bash
# Login to Azure
az login

# Set subscription if you have multiple
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Upload theme configs to Blob
az storage blob upload-batch \
  --account-name cvgeneratorstore \
  --destination cv-themes \
  --source templates/themes \
  --overwrite

# Upload HTML templates to Blob
az storage blob upload-batch \
  --account-name cvgeneratorstore \
  --destination cv-templates \
  --source templates/html \
  --overwrite
```

Or use the GitHub Actions workflow (see Step 5).

---

## Step 5: Deploy via GitHub Actions

### Automatic Deployment

Once secrets and workflow file (`.github/workflows/deploy-azure.yml`) are in place:

1. Commit and push to `main` branch
2. GitHub Actions automatically triggers
3. Runs tests, then deploys to Azure Functions
4. Uploads theme/template files to Blob Storage

**Deployment typically takes 3–5 minutes**

### View Deployment Status

- GitHub → Actions tab
- Click the latest workflow run
- Check "Deploy to Azure Functions" step

### View Function App Logs

```bash
az functionapp log tail --resource-group cv-generator-rg --name cv-generator
```

---

## Step 6: Test the Deployed API

### Get Function App URL

Azure Portal → Function Apps → cv-generator → Functions → generate-cv → Get Function URL

Typically: `https://cv-generator.azurewebsites.net/api/generate-cv?code=FUNCTION_KEY`

### Get Function Key

```bash
az functionapp keys list --resource-group cv-generator-rg --name cv-generator
```

### Test Endpoint

```bash
curl -X POST https://cv-generator.azurewebsites.net/api/generate-cv \
  -H "Content-Type: application/json" \
  -d @- << 'EOF'
{
  "cv_data": {
    "full_name": "Test User",
    "email": "test@example.com",
    "address_lines": ["City, Country"],
    "profile": "Test profile",
    "work_experience": [],
    "education": [],
    "languages": [],
    "it_ai_skills": [],
    "further_experience": [],
    "interests": ""
  },
  "theme": "zurich"
}
EOF
```

---

## Step 7: Monitor & Troubleshoot

### Application Insights

Azure Portal → Application Insights → cv-generator-insights

View:
- Live metrics
- Performance counters
- Custom dimensions (theme usage)
- Failures & exceptions

### Common Issues

**Issue: `StorageConnectionStringInvalid`**
- Verify `STORAGE_CONNECTION_STRING` is correct in Application Settings
- Ensure storage account access is enabled

**Issue: `Theme not found`**
- Check that theme files exist in Blob container `cv-themes`
- Run upload batch command again: `az storage blob upload-batch ...`

**Issue: `Playwright binary not found`**
- Function might be running on wrong OS (ensure Linux runtime)
- Clear site extensions cache: Azure Portal → Function App → Advanced Tools → CMD

**Issue: Deployment timeout**
- Check requirements.txt doesn't have incompatible dependencies
- Try increasing timeout in host.json (already set to 10 minutes)

---

## Step 8: Integration with Custom GPT

### OpenAPI Schema

Provide Custom GPT with the Function App endpoint + OpenAPI spec:

```
Base URL: https://cv-generator.azurewebsites.net/api
Schema: https://cv-generator.azurewebsites.net/api/openapi-schema
```

(Add `/openapi-schema` endpoint if needed for Custom GPT discovery)

### Test with Custom GPT

1. Create Custom GPT Actions integration
2. Set base URL to Function App endpoint
3. Include function key in Authorization header
4. Test "Generate PDF" action

---

## Step 9: Update Custom GPT System Prompt

Example prompt for Custom GPT:

```
You are a CV Generation Assistant.

When user provides CV information:
1. Extract and normalize to JSON matching the spec
2. Call /api/generate-cv with theme selector
3. Return PDF to user

Available themes: zurich, pink, modern (check /api/themes for latest)

Default: zurich (clean Swiss style)
```

---

## Scaling & Cost Optimization

### Flex Consumption Plan (Recommended)

- **Cost**: ~$0.000015/GB-second (pay only for used compute)
- **Scale**: Auto-scale to meet demand
- **Cold start**: ~2–5 seconds first invocation

### Alternative: Premium Plan

- Use if: Always-on needed, consistent traffic
- Cost: ~$200–300/month base

### Cost Estimation (Flex Consumption)

- 100 CVs/day × 0.5s render × 512MB = ~$2–3/month
- 1000 CVs/day = $20–30/month

---

## Troubleshooting Checklist

- [ ] Function App is running (Status = "Running")
- [ ] Storage account accessible from Function App
- [ ] Theme/template files exist in Blob containers
- [ ] Application Settings configured correctly
- [ ] `STORAGE_CONNECTION_STRING` is valid
- [ ] Python version matches (3.11)
- [ ] Requirements.txt has all dependencies
- [ ] GitHub Actions workflow shows green checkmark
- [ ] Custom GPT can reach endpoint with function key

---

## Next Steps

1. **Local testing**: `az functionapp start --local`
2. **Deploy via GitHub Actions**: Push to main
3. **Monitor**: Set up alerts in Application Insights
4. **Iterate**: Add new themes, optimize performance

---

**Questions?** Check OmniFlow Central's README for similar deployment patterns.
