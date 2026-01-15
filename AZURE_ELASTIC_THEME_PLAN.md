# Azure-Native Elastic CV Generator - Implementation Plan

**Version:** 1.0  
**Date:** January 16, 2026  
**Status:** Planning / Awaiting Approval

---

## Executive Summary

Transform the current fixed CV generator into an elastic, theme-driven system where:
- **Custom GPT** sends deterministic JSON + theme selector
- **Azure Function** renders PDF using theme configs stored in Blob Storage
- **Themes** are JSON configs (no code changes per theme)
- **Visual copy approach** for new templates (manually recreate layouts, 98% match)
- **Deterministic output** (same JSON → same PDF)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Custom GPT                                             │
│  "I want a modern tech CV with sidebar layout"          │
└────────────┬────────────────────────────────────────────┘
             │ HTTPS
             ▼
    ┌─────────────────────────────────────────────────────┐
    │  Azure Function App (Consumption Plan)              │
    │  ┌─────────────────────────────────────────────┐    │
    │  │ HTTP Trigger: /generate-cv                  │    │
    │  │ HTTP Trigger: /themes (list available)      │    │
    │  │ HTTP Trigger: /preview-html                 │    │
    │  └─────────────────────────────────────────────┘    │
    └────────────┬──────────────────────┬─────────────────┘
                 │                      │
                 │                      │ Read theme configs
                 │                      ▼
                 │            ┌──────────────────────────┐
                 │            │  Azure Blob Storage      │
                 │            │  Container: themes/      │
                 │            │    - zurich.json         │
                 │            │    - modern.json         │
                 │            │    - pink.json           │
                 │            │  Container: templates/   │
                 │            │    - cv_base.html        │
                 │            │    - cv_base.css         │
                 │            │  Container: fonts/       │
                 │            │    - custom fonts        │
                 │            └──────────────────────────┘
                 │
                 │ Render pipeline
                 ▼
    ┌─────────────────────────────┐
    │  Playwright (Chromium)      │
    │  HTML → PDF + DoD checks    │
    └────────────┬────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  Return PDF (base64)        │
    │  OR store in Blob + return  │
    │  signed URL (optional)      │
    └─────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Theme System Foundation (3–4 hours)

**Objective:** Externalize all styling to JSON configs stored in Blob Storage.

#### 1.1 Theme JSON Schema

Create `templates/themes/_schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["id", "name", "version", "colors", "fonts", "spacing", "layout"],
  "properties": {
    "id": { 
      "type": "string", 
      "pattern": "^[a-z0-9_-]+$",
      "description": "Unique theme identifier (lowercase, alphanumeric, hyphens)"
    },
    "name": { 
      "type": "string",
      "description": "Human-readable theme name"
    },
    "version": { 
      "type": "string", 
      "pattern": "^\\d+\\.\\d+\\.\\d+$",
      "description": "Semantic version (e.g., 1.0.0)"
    },
    "description": { 
      "type": "string",
      "description": "Theme description for UI display"
    },
    "preview_url": { 
      "type": "string",
      "description": "URL to theme preview image"
    },
    "colors": {
      "type": "object",
      "required": ["accent", "text", "background"],
      "properties": {
        "accent": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },
        "text": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },
        "muted": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },
        "border": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },
        "background": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" }
      }
    },
    "fonts": {
      "type": "object",
      "properties": {
        "main": { "type": "string" },
        "size_body": { "type": "string", "pattern": "^\\d+(\\.\\d+)?pt$" },
        "size_name": { "type": "string", "pattern": "^\\d+(\\.\\d+)?pt$" },
        "size_section": { "type": "string", "pattern": "^\\d+(\\.\\d+)?pt$" }
      }
    },
    "spacing": {
      "type": "object",
      "properties": {
        "section_gap_mm": { "type": "number", "minimum": 0 },
        "margin_top_mm": { "type": "number", "minimum": 0 },
        "margin_right_mm": { "type": "number", "minimum": 0 },
        "margin_bottom_mm": { "type": "number", "minimum": 0 },
        "margin_left_mm": { "type": "number", "minimum": 0 }
      }
    },
    "photo": {
      "type": "object",
      "properties": {
        "width_mm": { "type": "number", "minimum": 0 },
        "height_mm": { "type": "number", "minimum": 0 },
        "border_color": { "type": "string", "pattern": "^#[0-9a-fA-F]{6}$" },
        "border_width_pt": { "type": "number", "minimum": 0 },
        "shadow": { "type": "string" }
      }
    },
    "layout": {
      "type": "object",
      "properties": {
        "type": { 
          "enum": ["single-column", "sidebar", "two-column"],
          "description": "Layout structure type"
        },
        "page_break_after_section": { 
          "type": "string",
          "description": "Section name after which to insert page break"
        },
        "header_style": { 
          "enum": ["centered", "left-aligned", "split"],
          "description": "Header layout style"
        },
        "sidebar_position": {
          "enum": ["left", "right"],
          "description": "Sidebar position (for sidebar layout)"
        },
        "sidebar_width_mm": {
          "type": "number",
          "description": "Sidebar width in mm (for sidebar layout)"
        }
      }
    },
    "dod": {
      "type": "object",
      "description": "Definition of Done validation rules",
      "properties": {
        "max_pages": { 
          "type": "integer", 
          "minimum": 1, 
          "maximum": 3,
          "description": "Maximum allowed pages"
        },
        "expected_section_pages": { 
          "type": "object",
          "description": "Expected page number for each section",
          "additionalProperties": { "type": "integer" }
        }
      }
    }
  }
}
```

#### 1.2 Baseline Theme (Zurich)

Create `templates/themes/zurich.v1.0.0.json`:

```json
{
  "id": "zurich",
  "name": "Zurich Professional",
  "version": "1.0.0",
  "description": "Clean Swiss-style CV template with traditional layout",
  "preview_url": "https://cvgeneratorstore.blob.core.windows.net/previews/zurich.png",
  "colors": {
    "accent": "#0000ff",
    "text": "#000000",
    "muted": "#333333",
    "border": "#d8d8d8",
    "background": "#ffffff"
  },
  "fonts": {
    "main": "Arial, Helvetica, sans-serif",
    "size_body": "11pt",
    "size_name": "16pt",
    "size_section": "11pt"
  },
  "spacing": {
    "section_gap_mm": 6,
    "bullet_indent_mm": 5,
    "margin_top_mm": 20,
    "margin_right_mm": 22.4,
    "margin_bottom_mm": 20,
    "margin_left_mm": 25
  },
  "photo": {
    "width_mm": 45,
    "height_mm": 55,
    "border_color": "#d8d8d8",
    "border_width_pt": 0.5,
    "shadow": "0 1pt 3pt rgba(0, 0, 0, 0.08)"
  },
  "layout": {
    "type": "single-column",
    "page_break_after_section": "work_experience",
    "header_style": "split"
  },
  "dod": {
    "max_pages": 2,
    "expected_section_pages": {
      "Education": 1,
      "Work experience": 1,
      "Further experience / commitment": 2,
      "Language Skills": 2,
      "IT & AI Skills": 2,
      "Interests": 2,
      "References": 2
    }
  }
}
```

#### 1.3 Example Alternative Theme (Pink Minimalist)

Create `templates/themes/pink.v1.0.0.json`:

```json
{
  "id": "pink",
  "name": "Pink Minimalist",
  "version": "1.0.0",
  "description": "Modern minimalist CV with pink accent color",
  "preview_url": "https://cvgeneratorstore.blob.core.windows.net/previews/pink.png",
  "colors": {
    "accent": "#e91e63",
    "text": "#2c2c2c",
    "muted": "#757575",
    "border": "#fce4ec",
    "background": "#ffffff"
  },
  "fonts": {
    "main": "Helvetica, Arial, sans-serif",
    "size_body": "10.5pt",
    "size_name": "18pt",
    "size_section": "12pt"
  },
  "spacing": {
    "section_gap_mm": 7,
    "bullet_indent_mm": 4,
    "margin_top_mm": 18,
    "margin_right_mm": 20,
    "margin_bottom_mm": 18,
    "margin_left_mm": 20
  },
  "photo": {
    "width_mm": 40,
    "height_mm": 50,
    "border_color": "#e91e63",
    "border_width_pt": 1.5,
    "shadow": "0 2pt 8pt rgba(233, 30, 99, 0.15)"
  },
  "layout": {
    "type": "single-column",
    "page_break_after_section": "work_experience",
    "header_style": "split"
  },
  "dod": {
    "max_pages": 2,
    "expected_section_pages": {
      "Education": 1,
      "Work experience": 1,
      "Further experience / commitment": 2,
      "Language Skills": 2,
      "IT & AI Skills": 2,
      "Interests": 2,
      "References": 2
    }
  }
}
```

#### 1.4 Blob Storage Structure

```
storage account: cvgeneratorstore
├── themes/                    # Theme configs (JSON)
│   ├── zurich.v1.0.0.json
│   ├── modern.v1.0.0.json
│   ├── pink.v1.0.0.json
│   └── _schema.json
├── templates/                 # HTML/CSS templates
│   ├── cv_base.html
│   ├── cv_base.css
│   ├── cv_sidebar.html        # For sidebar layouts
│   └── cv_sidebar.css
├── fonts/                     # Custom web fonts (optional)
│   └── arial.woff2
└── generated/ (optional)      # Temporary PDFs (TTL: 1 hour)
    └── {request_id}.pdf
```

#### 1.5 Theme Loader Module

Create `src/theme_loader.py`:

```python
"""
Theme Loader - Load and cache theme configurations from Azure Blob Storage
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


class ThemeLoader:
    """Load theme configurations from Azure Blob Storage with caching."""
    
    def __init__(self, connection_string: Optional[str] = None):
        """Initialize Blob Storage client."""
        if connection_string:
            self.client = BlobServiceClient.from_connection_string(connection_string)
        else:
            account_url = os.getenv(
                "STORAGE_ACCOUNT_URL", 
                "https://cvgeneratorstore.blob.core.windows.net"
            )
            self.client = BlobServiceClient(
                account_url=account_url,
                credential=DefaultAzureCredential()
            )
    
    @lru_cache(maxsize=32)  # Cache hot themes in memory
    def load_theme(self, theme_id: str, version: str = "latest") -> dict:
        """
        Load theme configuration from Blob Storage.
        
        Args:
            theme_id: Theme identifier (e.g., "zurich", "pink")
            version: Theme version ("latest" or semantic version like "1.0.0")
        
        Returns:
            Theme configuration dict
        
        Raises:
            ValueError: If theme not found
        """
        container = self.client.get_container_client("themes")
        
        if version == "latest":
            # List all versions, pick highest semver
            blobs = list(container.list_blobs(name_starts_with=f"{theme_id}.v"))
            if not blobs:
                raise ValueError(f"Theme '{theme_id}' not found")
            
            # Sort by version (simple string sort works for semver)
            versions = sorted([b.name for b in blobs], reverse=True)
            blob_name = versions[0]
        else:
            blob_name = f"{theme_id}.v{version}.json"
        
        blob = container.get_blob_client(blob_name)
        
        try:
            data = blob.download_blob().readall()
            return json.loads(data)
        except Exception as e:
            raise ValueError(f"Failed to load theme '{theme_id}' version '{version}': {e}")
    
    def list_themes(self) -> list[dict]:
        """
        List all available themes with metadata.
        
        Returns:
            List of theme metadata dicts
        """
        container = self.client.get_container_client("themes")
        blobs = container.list_blobs()
        
        themes = []
        seen = set()
        
        for blob in blobs:
            if blob.name == "_schema.json":
                continue
            
            # Extract theme_id from blob name (format: theme_id.vX.Y.Z.json)
            theme_id = blob.name.split(".v")[0]
            
            if theme_id not in seen:
                try:
                    theme_data = self.load_theme(theme_id)
                    themes.append({
                        "id": theme_id,
                        "name": theme_data["name"],
                        "version": theme_data["version"],
                        "description": theme_data.get("description", ""),
                        "preview_url": theme_data.get("preview_url")
                    })
                    seen.add(theme_id)
                except Exception:
                    # Skip invalid themes
                    continue
        
        return themes
    
    def load_template(self, template_name: str) -> str:
        """
        Load HTML template from Blob Storage.
        
        Args:
            template_name: Template filename (e.g., "cv_base.html")
        
        Returns:
            Template HTML content
        """
        container = self.client.get_container_client("templates")
        blob = container.get_blob_client(template_name)
        
        try:
            data = blob.download_blob().readall()
            return data.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to load template '{template_name}': {e}")
```

#### 1.6 Convert CSS to Use Variables

Update `templates/html/cv_template_2pages_2025.css`:
- Replace hardcoded colors with `var(--accent)`, `var(--text)`, etc.
- Replace hardcoded sizes with `var(--font-size-body)`, etc.
- Replace hardcoded spacing with `var(--section-gap)`, etc.

**Deliverables:**
- [ ] JSON schema for themes
- [ ] Zurich theme as JSON baseline
- [ ] Example alternative theme (pink)
- [ ] Theme loader module
- [ ] CSS converted to variables

---

### Phase 2: Azure Function App Setup (2–3 hours)

**Objective:** Deploy API to Azure Functions with Blob Storage integration.

#### 2.1 Infrastructure as Code (Bicep)

Create `infra/main.bicep`:

```bicep
param location string = resourceGroup().location
param appName string = 'cv-generator'
param storageAccountName string = '${appName}store'

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

// Blob Services
resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

// Containers
resource themesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'themes'
  properties: { publicAccess: 'None' }
}

resource templatesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'templates'
  properties: { publicAccess: 'None' }
}

resource fontsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobServices
  name: 'fonts'
  properties: { publicAccess: 'None' }
}

// App Service Plan (Consumption)
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: '${appName}-plan'
  location: location
  sku: { name: 'Y1', tier: 'Dynamic' }
  properties: { reserved: true }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${appName}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    RetentionInDays: 30
  }
}

// Function App
resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: '${appName}-func'
  location: location
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'STORAGE_ACCOUNT_URL', value: storageAccount.properties.primaryEndpoints.blob }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'PLAYWRIGHT_BROWSERS_PATH', value: '/home/site/wwwroot/.playwright' }
      ]
    }
  }
  identity: { type: 'SystemAssigned' }
}

// Role Assignment: Grant Function App Blob Data Reader
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(storageAccount.id, functionApp.id, 'BlobDataReader')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
    principalId: functionApp.identity.principalId
  }
}

output functionAppName string = functionApp.name
output storageAccountName string = storageAccount.name
output appInsightsName string = appInsights.name
```

#### 2.2 Function App Entry Point

Create `function_app.py`:

```python
"""
Azure Function App - CV Generator API
"""
import os
import json
import base64
import logging

import azure.functions as func
from opencensus.ext.azure.log_exporter import AzureLogHandler

from src.theme_loader import ThemeLoader
from src.render import render_pdf
from src.validator import validate_cv
from src.normalize import normalize_cv_data
from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes

# Configure logging
logger = logging.getLogger(__name__)
if conn_str := os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    logger.addHandler(AzureLogHandler(connection_string=conn_str))

# Initialize theme loader
theme_loader = ThemeLoader()

app = func.FunctionApp()


@app.route(route="generate-cv", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def generate_cv(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate CV PDF from JSON data + theme.
    
    Payload:
        {
            "cv_data": { ... },
            "theme": "zurich",  // optional, defaults to "zurich"
            "source_docx_base64": "..."  // optional, for photo extraction
        }
    """
    try:
        payload = req.get_json()
        cv_data = payload.get("cv_data", payload)
        theme_id = payload.get("theme", "zurich")
        source_docx_b64 = payload.get("source_docx_base64")
        
        logger.info(f"Generate CV request: theme={theme_id}", extra={"custom_dimensions": {"theme": theme_id}})
        
        # Load theme from Blob Storage
        theme_config = theme_loader.load_theme(theme_id)
        
        # Extract photo from source DOCX if provided
        if source_docx_b64 and not cv_data.get("photo_url"):
            try:
                docx_bytes = base64.b64decode(source_docx_b64)
                photo_uri = extract_first_photo_data_uri_from_docx_bytes(docx_bytes)
                if photo_uri:
                    cv_data["photo_url"] = photo_uri
            except Exception as e:
                logger.warning(f"Photo extraction failed: {e}")
        
        # Normalize + validate
        cv_data = normalize_cv_data(cv_data)
        validation = validate_cv(cv_data)
        
        if not validation.is_valid:
            error_details = [
                {
                    "field": e.field,
                    "current": e.current_value,
                    "limit": e.limit,
                    "message": e.message,
                    "suggestion": e.suggestion
                }
                for e in validation.errors
            ]
            return func.HttpResponse(
                json.dumps({
                    "error": "Validation failed",
                    "estimated_pages": validation.estimated_pages,
                    "validation_errors": error_details
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Render PDF
        pdf_bytes = render_pdf(cv_data, theme_config)
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        
        filename = f"{cv_data.get('full_name', 'CV').replace(' ', '_')}.pdf"
        
        logger.info(f"PDF generated: {len(pdf_bytes)} bytes")
        
        return func.HttpResponse(
            json.dumps({
                "pdf_base64": pdf_b64,
                "filename": filename,
                "pages": theme_config.get("dod", {}).get("max_pages", 2)
            }),
            mimetype="application/json"
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logger.exception("Unexpected error")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error", "message": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="themes", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def list_themes(req: func.HttpRequest) -> func.HttpResponse:
    """List all available themes."""
    try:
        themes = theme_loader.list_themes()
        return func.HttpResponse(
            json.dumps({"themes": themes}),
            mimetype="application/json"
        )
    except Exception as e:
        logger.exception("Failed to list themes")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="preview-html", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def preview_html(req: func.HttpRequest) -> func.HttpResponse:
    """Generate HTML preview (for debugging)."""
    try:
        from src.render import render_html
        
        payload = req.get_json()
        cv_data = payload.get("cv_data", payload)
        theme_id = payload.get("theme", "zurich")
        
        theme_config = theme_loader.load_theme(theme_id)
        cv_data = normalize_cv_data(cv_data)
        
        html = render_html(cv_data, theme_config)
        
        return func.HttpResponse(html, mimetype="text/html")
    except Exception as e:
        logger.exception("Failed to generate HTML preview")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
```

#### 2.3 Update Requirements

Update `requirements.txt`:

```
jinja2>=3.1.0
playwright>=1.57.0
flask>=3.0.0
flask-cors>=4.0.0
PyPDF2>=3.0.0
python-docx>=1.1.2
azure-functions>=1.18.0
azure-storage-blob>=12.19.0
azure-identity>=1.15.0
opencensus-ext-azure>=1.1.11
```

**Deliverables:**
- [ ] Bicep infrastructure definition
- [ ] Function App entry point
- [ ] Updated requirements.txt
- [ ] Local testing setup

---

### Phase 3: Template Flexibility (4–5 hours)

**Objective:** Support multiple layout types (single-column, sidebar, two-column) with same JSON.

#### 3.1 Update Render Module

Modify `src/render.py` to support theme-driven rendering:

```python
# Key changes:
# 1. Accept theme_config parameter
# 2. Select template based on layout type
# 3. Inject CSS variables from theme
# 4. Load DoD expectations from theme

def generate_css_variables(theme: dict) -> str:
    """Generate CSS custom properties from theme config."""
    colors = theme.get("colors", {})
    fonts = theme.get("fonts", {})
    spacing = theme.get("spacing", {})
    photo = theme.get("photo", {})
    
    return f"""
    :root {{
      --accent: {colors.get('accent', '#0000ff')};
      --text: {colors.get('text', '#000000')};
      --muted: {colors.get('muted', '#333333')};
      --border: {colors.get('border', '#d8d8d8')};
      --bg: {colors.get('background', '#ffffff')};
      --font-main: {fonts.get('main', 'Arial, sans-serif')};
      --font-size-body: {fonts.get('size_body', '11pt')};
      --font-size-name: {fonts.get('size_name', '16pt')};
      --font-size-section: {fonts.get('size_section', '11pt')};
      --section-gap: {spacing.get('section_gap_mm', 6)}mm;
      --photo-width: {photo.get('width_mm', 45)}mm;
      --photo-height: {photo.get('height_mm', 55)}mm;
      --photo-border-color: {photo.get('border_color', '#d8d8d8')};
      --photo-border-width: {photo.get('border_width_pt', 0.5)}pt;
      --photo-shadow: {photo.get('shadow', 'none')};
      /* Add all other spacing vars */
    }}
    """

def render_html(cv: dict, theme_config: dict, inline_css: bool = True) -> str:
    """Render CV HTML using theme configuration."""
    # Normalize input
    cv = normalize_cv_data(cv)
    
    # Select template based on layout type
    layout_type = theme_config.get("layout", {}).get("type", "single-column")
    
    if layout_type == "sidebar":
        template_name = "cv_sidebar.html"
    elif layout_type == "two-column":
        template_name = "cv_two_column.html"
    else:
        template_name = "cv_base.html"
    
    # Load template
    # (Try Blob first, fallback to bundled)
    
    # Generate CSS variables
    css_vars = generate_css_variables(theme_config)
    
    # Render with Jinja2
    # ...
```

#### 3.2 Create Sidebar Layout Template

Create `templates/html/cv_sidebar.html` and `cv_sidebar.css`.

**Deliverables:**
- [ ] Updated render.py with theme support
- [ ] CSS variable injection
- [ ] Sidebar layout template (optional, can be done later)
- [ ] Theme-aware DoD checks

---

### Phase 4: CI/CD Pipeline (2 hours)

**Objective:** Automated deployment from GitHub → Azure.

#### 4.1 GitHub Actions Workflow

Create `.github/workflows/deploy-azure.yml`:

```yaml
name: Deploy to Azure Functions

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  AZURE_FUNCTIONAPP_NAME: cv-generator-func
  PYTHON_VERSION: '3.11'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Install Python dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
      
      - name: Install Node dependencies
        run: npm ci
      
      - name: Run tests
        run: npm test
  
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
      
      - name: Deploy to Azure Functions
        uses: Azure/functions-action@v1
        with:
          app-name: ${{ env.AZURE_FUNCTIONAPP_NAME }}
          package: .
          publish-profile: ${{ secrets.AZURE_FUNCTIONAPP_PUBLISH_PROFILE }}
      
      - name: Upload themes to Blob Storage
        uses: azure/CLI@v1
        with:
          inlineScript: |
            az storage blob upload-batch \
              --account-name cvgeneratorstore \
              --destination themes \
              --source templates/themes \
              --auth-mode login \
              --overwrite
            
            az storage blob upload-batch \
              --account-name cvgeneratorstore \
              --destination templates \
              --source templates/html \
              --auth-mode login \
              --overwrite
```

**Deliverables:**
- [ ] GitHub Actions workflow
- [ ] Secrets configured in GitHub
- [ ] Deployment tested

---

### Phase 5: Monitoring & Observability (1 hour)

**Objective:** Track usage, errors, performance.

#### 5.1 Application Insights Integration

Already included in `function_app.py` via `opencensus-ext-azure`.

#### 5.2 Key Metrics to Track

- **Theme usage**: Which themes are requested most
- **Generation time**: PDF render latency (p50, p95, p99)
- **Validation failures**: Content exceeding limits
- **Photo extraction**: Success/failure rate
- **Errors**: 4xx/5xx breakdown

#### 5.3 Kusto Queries (Example)

```kql
// Theme popularity
customEvents
| where name == "Generate CV request"
| extend theme = tostring(customDimensions.theme)
| summarize count() by theme
| order by count_ desc

// Render latency
requests
| where name == "generate-cv"
| summarize p50=percentile(duration, 50), p95=percentile(duration, 95) by bin(timestamp, 1h)
| render timechart
```

**Deliverables:**
- [ ] Application Insights queries
- [ ] Dashboard for key metrics
- [ ] Alerts for errors/latency

---

## Final File Structure

```
cv-generator-repo/
├── .github/
│   └── workflows/
│       └── deploy-azure.yml        # CI/CD pipeline
├── infra/
│   └── main.bicep                  # Azure infrastructure
├── src/
│   ├── theme_loader.py             # NEW: Load themes from Blob
│   ├── render.py                   # MODIFIED: Theme-aware rendering
│   ├── validator.py                # UNCHANGED
│   ├── normalize.py                # UNCHANGED
│   └── docx_photo.py               # UNCHANGED
├── templates/
│   ├── themes/                     # Theme configs (uploaded to Blob)
│   │   ├── _schema.json
│   │   ├── zurich.v1.0.0.json
│   │   ├── modern.v1.0.0.json
│   │   └── pink.v1.0.0.json
│   └── html/                       # Template files (uploaded to Blob)
│       ├── cv_base.html            # MODIFIED: CSS variables
│       ├── cv_base.css             # MODIFIED: CSS variables
│       ├── cv_sidebar.html         # NEW: Sidebar layout (optional)
│       └── cv_sidebar.css          # NEW
├── tests/
│   ├── cv-visual.spec.ts           # MODIFIED: Multi-theme tests
│   └── test_theme_loader.py        # NEW: Theme validation tests
├── function_app.py                 # NEW: Azure Functions entry point
├── host.json                       # NEW: Function App config
├── requirements.txt                # UPDATED: Add Azure libs
├── api.py                          # KEEP: Local Flask for development
└── README.md
```

---

## Time Estimate

| Phase | Time | Status |
|-------|------|--------|
| Phase 1: Theme system | 3–4 hours | 🔲 Pending |
| Phase 2: Azure Functions | 2–3 hours | 🔲 Pending |
| Phase 3: Template flexibility | 4–5 hours | 🔲 Pending |
| Phase 4: CI/CD | 2 hours | 🔲 Pending |
| Phase 5: Monitoring | 1 hour | 🔲 Pending |
| **Total** | **12–15 hours** | |

---

## Key Benefits

✅ **Config-driven themes** (JSON in Blob, no code changes per theme)  
✅ **Versioned themes** (rollback, A/B testing)  
✅ **Scalable** (Azure Functions auto-scale)  
✅ **Cost-optimized** (Consumption plan = pay-per-request)  
✅ **Secure** (Managed Identity for Blob access)  
✅ **Observable** (Application Insights)  
✅ **Visual copy approach** (manually recreate layouts, 98% match)  
✅ **Deterministic** (same JSON → same PDF)

---

## Approval Questions

Before implementation, please confirm:

1. **Blob vs bundled templates**  
   Should templates live ONLY in Blob, or bundle them in function deployment as fallback?  
   **Recommendation:** Blob primary, bundled fallback (resilience)

2. **PDF storage**  
   Return PDF directly (base64) or store in Blob + return signed URL?  
   **Recommendation:** Base64 for simplicity (Custom GPT handles it natively)

3. **Theme versioning strategy**  
   Semantic versioning (v1.0.0) or timestamp-based?  
   **Recommendation:** Semantic versioning (clearer intent)

4. **Custom GPT integration**  
   Expose `/themes` publicly or keep it authenticated?  
   **Recommendation:** Authenticated (func key) to prevent abuse

5. **Local dev workflow**  
   Keep current Flask API for local testing, deploy to Functions for prod?  
   **Recommendation:** Yes (dual-mode: Flask local, Functions prod)

---

## Next Steps

Upon approval:
1. Start with **Phase 1** (theme extraction + JSON schema)
2. Test theme-driven rendering locally with Flask
3. Deploy infrastructure with Bicep
4. Implement Functions + CI/CD
5. Add monitoring + dashboards

---

**Status:** ✅ Plan documented, awaiting approval to proceed
