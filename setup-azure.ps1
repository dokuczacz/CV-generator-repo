# CV Generator - Azure Deployment Automation Script
# Mirrors OmniFlow Central pattern for consistency

param(
    [string]$EnvironmentName = "dev",
    [string]$Location = "westeurope",
    [string]$ResourceGroupName = "cv-generator-rg",
    [string]$StorageAccountName = "cvgeneratorstore2025",
    [string]$FunctionAppName = "cv-generator"
)

Write-Host "=== CV Generator Azure Deployment (OmniFlow Pattern) ===" -ForegroundColor Cyan

# 1. Login
Write-Host "`n[1/11] Logging in to Azure..." -ForegroundColor Yellow
az login --query "id" | Out-Null
Write-Host "✓ Logged in successfully" -ForegroundColor Green

# 2. Create Resource Group
Write-Host "`n[2/11] Creating resource group: $ResourceGroupName..." -ForegroundColor Yellow
az group create --name $ResourceGroupName --location $Location | Out-Null
Write-Host "✓ Resource group created" -ForegroundColor Green

# 3. Create Storage Account
Write-Host "`n[3/11] Creating storage account: $StorageAccountName..." -ForegroundColor Yellow
az storage account create `
  --name $StorageAccountName `
  --resource-group $ResourceGroupName `
  --location $Location `
  --sku Standard_LRS | Out-Null
Write-Host "✓ Storage account created" -ForegroundColor Green

# 4. Get Storage Connection String
Write-Host "`n[4/11] Retrieving storage connection string..." -ForegroundColor Yellow
$StorageConnString = az storage account show-connection-string `
  --resource-group $ResourceGroupName `
  --name $StorageAccountName `
  --query connectionString -o tsv
Write-Host "✓ Connection string retrieved" -ForegroundColor Green

# 5. Create Blob Containers
Write-Host "`n[5/11] Creating blob containers..." -ForegroundColor Yellow
@("cv-themes", "cv-templates", "cv-fonts") | ForEach-Object {
    az storage container create `
      --name $_ `
      --account-name $StorageAccountName 2>&1 | Out-Null
    Write-Host "  ✓ Container '$_' created"
}

# 6. Create Function App
Write-Host "`n[6/11] Creating Azure Functions app: $FunctionAppName..." -ForegroundColor Yellow
az functionapp create `
  --resource-group $ResourceGroupName `
  --consumption-plan-location $Location `
  --runtime python `
  --runtime-version 3.11 `
  --functions-version 4 `
  --name $FunctionAppName `
  --storage-account $StorageAccountName `
  --sku FlexConsumption 2>&1 | Out-Null
Write-Host "✓ Function app created (FlexConsumption, Python 3.11)" -ForegroundColor Green

# 7. Download Publish Profile
Write-Host "`n[7/11] Downloading publish profile..." -ForegroundColor Yellow
$PublishProfilePath = "$PWD\cv-generator-publish-profile.xml"
az functionapp deployment list-publishing-profiles `
  --resource-group $ResourceGroupName `
  --name $FunctionAppName `
  --xml > $PublishProfilePath
Write-Host "✓ Publish profile saved to: $PublishProfilePath" -ForegroundColor Green
Write-Host "  ** SAVE THIS FILE - you need it for GitHub secrets **"

# 8. Configure Function App Settings
Write-Host "`n[8/11] Configuring function app settings..." -ForegroundColor Yellow
az functionapp config appsettings set `
  --name $FunctionAppName `
  --resource-group $ResourceGroupName `
  --settings `
    STORAGE_ACCOUNT_URL="https://$StorageAccountName.blob.core.windows.net" `
    AZURE_BLOB_CONTAINER_THEMES="cv-themes" `
    AZURE_BLOB_CONTAINER_TEMPLATES="cv-templates" `
    AZURE_BLOB_CONTAINER_FONTS="cv-fonts" `
    CV_DEFAULT_THEME="zurich" `
    PLAYWRIGHT_BROWSERS_PATH="/home/site/wwwroot/.playwright" `
    AZURE_SDK_LOG_LEVEL="WARNING" | Out-Null
Write-Host "✓ Settings configured" -ForegroundColor Green

# 9. Upload Initial Theme Files
Write-Host "`n[9/11] Uploading theme and template files to Blob Storage..." -ForegroundColor Yellow

if (Test-Path "templates/themes") {
    az storage blob upload-batch `
      --account-name $StorageAccountName `
      --destination cv-themes `
      --source "templates/themes" `
      --overwrite 2>&1 | Out-Null
    Write-Host "  ✓ Themes uploaded"
} else {
    Write-Host "  ⚠ Warning: templates/themes directory not found" -ForegroundColor Yellow
}

if (Test-Path "templates/html") {
    az storage blob upload-batch `
      --account-name $StorageAccountName `
      --destination cv-templates `
      --source "templates/html" `
      --overwrite 2>&1 | Out-Null
    Write-Host "  ✓ Templates uploaded"
} else {
    Write-Host "  ⚠ Warning: templates/html directory not found" -ForegroundColor Yellow
}

# 10. Display GitHub Secrets Instructions
Write-Host "`n[10/11] GitHub Secrets Setup Instructions:" -ForegroundColor Yellow
Write-Host @"
  
  Go to: https://github.com/YOUR_REPO/settings/secrets/actions
  
  Add two secrets:
  
  1. AZURE_FUNCTIONAPP_PUBLISH_PROFILE
     - Copy entire contents of: $PublishProfilePath
     - Paste into GitHub secret
  
  2. STORAGE_CONNECTION_STRING
     - Copy this value:
     $StorageConnString
     - Paste into GitHub secret

"@

# 11. Summary
Write-Host "`n[11/11] Deployment Summary:" -ForegroundColor Cyan
Write-Host @"

  ✓ Resource Group: $ResourceGroupName
  ✓ Storage Account: $StorageAccountName
  ✓ Function App: $FunctionAppName (FlexConsumption)
  ✓ Blob Containers: cv-themes, cv-templates, cv-fonts
  ✓ Runtime: Python 3.11
  ✓ Publish Profile: $PublishProfilePath

  NEXT STEPS:
  
  1. Add the two GitHub secrets (copy-paste instructions above)
  
  2. Commit and push to main:
     git add .
     git commit -m 'setup: azure infrastructure from omniflow pattern'
     git push origin main
  
  3. GitHub Actions will automatically:
     - Run tests
     - Deploy function app
     - Upload themes/templates to Blob
  
  4. Verify deployment:
     https://cv-generator.azurewebsites.net/api/generate-cv

"@

Write-Host "Setup complete! 🚀" -ForegroundColor Green
