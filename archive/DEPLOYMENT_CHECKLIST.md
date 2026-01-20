# CV Generator - Azure Deployment Checklist

## ✅ Infrastructure Setup Complete

All necessary files copied from OmniFlow Central pattern:

- [x] `host.json` — Azure Functions runtime config
- [x] `local.settings.json` — Development environment settings  
- [x] `.funcignore` — Deployment exclusions
- [x] `.github/workflows/deploy-azure.yml` — CI/CD pipeline

## 📋 Pre-Deployment Checklist

### Step 1: Run Azure Setup Script
```powershell
cd c:\AI memory\CV-generator-repo
.\setup-azure.ps1
```

This script will:
- Create Resource Group: `cv-generator-rg`
- Create Storage Account: `cvgeneratorstore2025`
- Create 3 Blob Containers: cv-themes, cv-templates, cv-fonts
- Create Function App: `cv-generator` (FlexConsumption)
- Configure all settings
- Download publish profile
- Upload theme files

**Expected Duration**: 5–10 minutes

### Step 2: Add GitHub Secrets

Go to: **https://github.com/YOUR_REPO/settings/secrets/actions**

Add these two secrets:

**Secret 1: `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`**
- Source: The XML file created by setup script
- Instructions will be printed after script completes
- Paste the entire XML content (not the file path)

**Secret 2: `STORAGE_CONNECTION_STRING`**
- Source: Azure Storage Account connection string
- Instructions will be printed after script completes
- Copy-paste the connection string exactly

### Step 3: Trigger Deployment

```bash
cd c:\AI memory\CV-generator-repo
git add .
git commit -m "setup: azure infrastructure from omniflow pattern"
git push origin main
```

This triggers GitHub Actions which will:
1. Run tests (must pass)
2. Build Python package
3. Deploy to Azure Functions
4. Upload themes/templates to Blob Storage

**Expected Duration**: 5–10 minutes

### Step 4: Verify Deployment

Check **GitHub Actions** tab in your repository for workflow status.

Once complete, test the endpoint:

```bash
curl -X POST https://cv-generator.azurewebsites.net/api/generate-cv \
  -H "Content-Type: application/json" \
  -H "x-functions-key: $(az functionapp keys list --resource-group cv-generator-rg --name cv-generator --query "functionKeys.default" -o tsv)" \
  -d '{
    "cv_data": {
      "full_name": "Test User",
      "email": "test@example.com",
      "address_lines": ["City, Country"],
      "profile": "Test profile"
    },
    "theme": "zurich"
  }'
```

Expected response: PDF file or JSON with base64-encoded PDF.

### Step 5: Update Custom GPT Endpoint

Update Custom GPT Actions configuration:
- Old URL: `http://127.0.0.1:5000/api/...`
- New URL: `https://cv-generator.azurewebsites.net/api/...`

Test in Custom GPT to verify integration works.

## 📊 Expected Resources After Deployment

### Resource Group: `cv-generator-rg`

| Resource | Name | Status |
|----------|------|--------|
| Storage Account | `cvgeneratorstore2025` | ✓ Created |
| — Containers | cv-themes | ✓ Created |
| — | cv-templates | ✓ Created |
| — | cv-fonts | ✓ Created |
| Function App | cv-generator | ✓ Created (FlexConsumption) |
| Application Insights | cv-generator | ✓ Auto-created |

## 🔧 Configuration Applied

### Function App Settings
- `STORAGE_ACCOUNT_URL`: https://cvgeneratorstore2025.blob.core.windows.net
- `AZURE_BLOB_CONTAINER_THEMES`: cv-themes
- `AZURE_BLOB_CONTAINER_TEMPLATES`: cv-templates
- `AZURE_BLOB_CONTAINER_FONTS`: cv-fonts
- `CV_DEFAULT_THEME`: zurich
- `PLAYWRIGHT_BROWSERS_PATH`: /home/site/wwwroot/.playwright
- `AZURE_SDK_LOG_LEVEL`: WARNING

### Runtime
- Python: 3.11
- Functions Version: 4
- SKU: FlexConsumption (auto-scales, pay-per-use)

## 💰 Cost Estimation

**FlexConsumption Plan**
- ~$0.000015/GB-second (billing granularity: 100ms)
- Base: $0
- Execution: Pay only for used compute

**Expected Monthly Costs**
- 100 CVs/day: ~$2–3/month
- 1000 CVs/day: ~$20–30/month
- Storage: ~$0.01/month (minimal blob storage)

## 🚨 Troubleshooting

### Issue: "Missing required secret: AZURE_FUNCTIONAPP_PUBLISH_PROFILE"

**Solution**: 
1. Go to GitHub repo → Settings → Secrets and Variables
2. Verify both secrets exist and have correct names (case-sensitive)
3. Re-run the workflow manually: Actions → Deploy CV Generator → Run workflow

### Issue: "Function app not responding after deployment"

**Solution**:
1. Check Application Insights logs:
   ```bash
   az functionapp log tail --resource-group cv-generator-rg --name cv-generator
   ```
2. Verify Function App is running:
   ```bash
   az functionapp show --resource-group cv-generator-rg --name cv-generator
   ```
3. Check STORAGE_CONNECTION_STRING is valid in App Settings

### Issue: "Blob containers empty after deployment"

**Solution**:
1. Manually upload files:
   ```bash
   az storage blob upload-batch \
     --account-name cvgeneratorstore2025 \
     --destination cv-themes \
     --source templates/themes \
     --overwrite
   ```
2. Verify theme files are present:
   ```bash
   az storage blob list --account-name cvgeneratorstore2025 --container-name cv-themes
   ```

## 📚 References

- OmniFlow Central: Deployment pattern reference
- Azure Functions: https://learn.microsoft.com/en-us/azure/azure-functions/
- Azure Blob Storage: https://learn.microsoft.com/en-us/azure/storage/blobs/
- GitHub Actions: https://docs.github.com/en/actions

## ✨ Next Steps

After successful deployment:

1. **Add more themes** by uploading JSON configs to Blob Storage
2. **Monitor performance** via Application Insights
3. **Set up cost alerts** in Azure Portal
4. **Enable continuous integration** with custom GPT for live CV generation
