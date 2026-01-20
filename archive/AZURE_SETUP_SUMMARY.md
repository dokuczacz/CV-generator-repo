# CV Generator - Azure Deployment Summary

## ✅ What Was Done

Copied and adapted **OmniFlow Central's proven deployment infrastructure** for the CV Generator.

### Files Created/Configured

```
CV-generator-repo/
├── host.json                                    # Azure Functions config
├── local.settings.json                          # Dev environment settings
├── .funcignore                                  # Deployment exclusions
├── .github/workflows/deploy-azure.yml           # CI/CD pipeline
├── setup-azure.ps1                              # Automated setup script
├── AZURE_DEPLOYMENT.md                          # Deployment guide
├── AZURE_SETUP_FROM_OMNIFLOW.md                 # Step-by-step setup
├── DEPLOYMENT_CHECKLIST.md                      # Pre/post verification
└── DEPLOYMENT_GUIDE.md                          # Comprehensive guide
```

### Configuration Inherited from OmniFlow Central

| Component | Setting | Value |
|-----------|---------|-------|
| Runtime | Language | Python 3.11 |
| SKU | Plan | FlexConsumption |
| Timeout | | 10 minutes |
| Storage | Emulator | Azurite (dev) |
| Extensions | Bundle | v4 |

---

## 🚀 How to Deploy

### Step 1: Run Setup Script

```powershell
cd c:\AI memory\CV-generator-repo
.\setup-azure.ps1
```

**What it does:**
- Creates Azure resource group: `cv-generator-rg`
- Creates storage account: `cvgeneratorstore2025`
- Creates blob containers: cv-themes, cv-templates, cv-fonts
- Creates Function App: `cv-generator` (FlexConsumption)
- Uploads theme/template files
- Downloads publish profile
- Prints GitHub secrets instructions

**Duration**: ~10 minutes

### Step 2: Add GitHub Secrets

Go to: `https://github.com/YOUR_REPO/settings/secrets/actions`

Add two secrets (copy-paste from setup script output):

1. `AZURE_FUNCTIONAPP_PUBLISH_PROFILE` — XML content
2. `STORAGE_CONNECTION_STRING` — Connection string

### Step 3: Trigger Deployment

```bash
git add .
git commit -m "setup: azure infrastructure from omniflow pattern"
git push origin main
```

GitHub Actions automatically:
- Runs tests
- Builds & deploys Function App
- Uploads artifacts to Blob

**Duration**: ~5–10 minutes

**Status**: Check GitHub Actions tab

### Step 4: Verify

```bash
# Test endpoint
curl -X POST https://cv-generator.azurewebsites.net/api/generate-cv \
  -H "Content-Type: application/json" \
  -d '{"cv_data":{"full_name":"Test"},"theme":"zurich"}'
```

---

## 📊 Expected Resources

After setup script completes:

| Resource | Name | Type |
|----------|------|------|
| Resource Group | `cv-generator-rg` | Container |
| Storage Account | `cvgeneratorstore2025` | Cloud storage |
| Blob Container | `cv-themes` | Blob |
| Blob Container | `cv-templates` | Blob |
| Blob Container | `cv-fonts` | Blob |
| Function App | `cv-generator` | Serverless compute |
| App Service Plan | (auto-generated) | FlexConsumption |
| Application Insights | (auto-created) | Monitoring |

---

## 💰 Cost Estimate

- **Compute**: $0.000015/GB-second (pay-per-use)
- **Storage**: ~$0.01–0.05/month
- **100 CVs/day**: ~$2–3/month
- **1000 CVs/day**: ~$20–40/month

---

## 🔑 GitHub Secrets

### Secret 1: `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`
- Source: `cv-generator-publish-profile.xml` (from setup script)
- Content: Entire XML (starts with `<?xml...`)
- Expires: 180 days

### Secret 2: `STORAGE_CONNECTION_STRING`
- Source: Azure Portal / Setup script output
- Content: Connection string (starts with `DefaultEndpointsProtocol=...`)
- Expires: Never (but can be rotated)

---

## 🔄 CI/CD Pipeline

`.github/workflows/deploy-azure.yml` executes on every `git push origin main`:

```
┌─────────────────┐
│   npm test      │ ← Must pass
└────────┬────────┘
         ▼
┌─────────────────┐
│   Build Python  │ ← Install deps
└────────┬────────┘
         ▼
┌─────────────────┐
│   Deploy to     │ ← Push to Azure
│   Function App  │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Upload Blobs  │ ← Themes/templates
└─────────────────┘
```

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| `AZURE_DEPLOYMENT.md` | Comprehensive deployment guide |
| `AZURE_SETUP_FROM_OMNIFLOW.md` | Manual step-by-step setup |
| `DEPLOYMENT_CHECKLIST.md` | Pre/post-deployment verification |
| `setup-azure.ps1` | Automated setup script |

---

## 🎯 What's Next

1. **Run setup-azure.ps1** — Creates all resources
2. **Add GitHub secrets** — Copy-paste from script output
3. **Push to main** — Triggers automatic deployment
4. **Verify endpoint** — Test live API
5. **Update Custom GPT** — Point to new Azure endpoint

---

## 📞 Troubleshooting

### Setup script fails?
```bash
# Make sure you're in the right directory
cd c:\AI memory\CV-generator-repo

# Verify Azure CLI is installed
az --version

# Login first
az login
```

### GitHub Actions fails?
- Check secrets are added (Settings → Secrets)
- Verify secret names are exact (case-sensitive)
- Re-run workflow: Actions → Deploy → Run workflow

### Function App not responding?
```bash
# Check logs
az functionapp log tail --resource-group cv-generator-rg --name cv-generator

# Check status
az functionapp show --resource-group cv-generator-rg --name cv-generator
```

---

## ✨ Pattern Origin

This deployment infrastructure is based on **OmniFlow Central** — a proven production pattern for:
- Reliable Azure Functions deployment
- Automated CI/CD with GitHub Actions
- Cost-effective FlexConsumption pricing
- Blob Storage for artifacts
- Application Insights monitoring

By using the same pattern, CV Generator gets:
- Consistency across APIs
- Production-ready reliability
- Team familiarity
- Optimized costs

---

**Ready to deploy?** → Start with `.\setup-azure.ps1`

**Need help?** → See `AZURE_DEPLOYMENT.md` for detailed guide
