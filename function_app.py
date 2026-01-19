"""
Azure Functions app for CV Generator
Converts Flask endpoints to Azure HTTP triggers
"""

import azure.functions as func
import logging
import json
import base64
import io
from pathlib import Path
from dataclasses import asdict
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.render import render_pdf, render_html
from src.validator import validate_cv
from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes
from src.normalize import normalize_cv_data


def _serialize_validation_result(validation_result):
    """Convert ValidationResult to JSON-safe dict."""
    return {
        "is_valid": validation_result.is_valid,
        "errors": [asdict(err) for err in validation_result.errors],
        "warnings": validation_result.warnings,
        "estimated_pages": validation_result.estimated_pages,
        "estimated_height_mm": validation_result.estimated_height_mm,
        "details": validation_result.details,
    }

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    logging.info('Health check requested')
    
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "service": "CV Generator API",
            "version": "1.0"
        }),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="generate-cv", methods=["POST"])
def generate_cv(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate CV PDF from JSON data
    Returns PDF file directly
    """
    logging.info('Generate CV requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    cv_data = req_body.get("cv_data")
    if not cv_data:
        return func.HttpResponse(
            json.dumps({"error": "Missing cv_data in request"}),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize CV data (handle GPT variations)
    cv_data = normalize_cv_data(cv_data)
    
    # Extract photo if source DOCX provided
    source_docx_b64 = req_body.get("source_docx_base64")
    if source_docx_b64:
        try:
            docx_bytes = base64.b64decode(source_docx_b64)
            photo_data_uri = extract_first_photo_data_uri_from_docx_bytes(docx_bytes)
            if photo_data_uri:
                cv_data["photo_url"] = photo_data_uri
                logging.info("Photo extracted from source DOCX")
        except Exception as e:
            logging.warning(f"Failed to extract photo: {e}")
    
    # Validate CV data
    validation_result = validate_cv(cv_data)
    if not validation_result.is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "Validation failed",
                "validation": _serialize_validation_result(validation_result)
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Generate PDF
    try:
        pdf_bytes = render_pdf(cv_data)
        
        return func.HttpResponse(
            body=pdf_bytes,
            mimetype="application/pdf",
            status_code=200,
            headers={
                "Content-Disposition": "attachment; filename=cv.pdf"
            }
        )
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return func.HttpResponse(
            json.dumps({
                "error": "PDF generation failed",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="generate-cv-action", methods=["POST"])
def generate_cv_action(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate CV for Custom GPT Actions (returns JSON with base64 PDF)
    """
    logging.info('Generate CV Action requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    cv_data = req_body.get("cv_data")
    if not cv_data:
        return func.HttpResponse(
            json.dumps({"error": "Missing cv_data in request"}),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize CV data
    cv_data = normalize_cv_data(cv_data)
    
    # Extract photo if provided
    source_docx_b64 = req_body.get("source_docx_base64")
    if source_docx_b64:
        try:
            docx_bytes = base64.b64decode(source_docx_b64)
            photo_data_uri = extract_first_photo_data_uri_from_docx_bytes(docx_bytes)
            if photo_data_uri:
                cv_data["photo_url"] = photo_data_uri
        except Exception as e:
            logging.warning(f"Photo extraction failed: {e}")
    
    # Validate
    validation_result = validate_cv(cv_data)
    if not validation_result.is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "Validation failed",
                "validation": _serialize_validation_result(validation_result)
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Generate PDF
    try:
        pdf_bytes = render_pdf(cv_data)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "pdf_base64": pdf_base64,
                "validation": {
                    "warnings": validation_result.warnings,
                    "estimated_pages": validation_result.estimated_pages,
                    "errors": _serialize_validation_result(validation_result)["errors"]
                }
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return func.HttpResponse(
            json.dumps({
                "error": "PDF generation failed",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="preview-html", methods=["POST"])
def preview_html(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate HTML preview (no PDF rendering)
    """
    logging.info('Preview HTML requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    cv_data = req_body.get("cv_data")
    if not cv_data:
        return func.HttpResponse(
            json.dumps({"error": "Missing cv_data in request"}),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize
    cv_data = normalize_cv_data(cv_data)
    
    # Extract photo if provided
    source_docx_b64 = req_body.get("source_docx_base64")
    if source_docx_b64:
        try:
            docx_bytes = base64.b64decode(source_docx_b64)
            photo_data_uri = extract_first_photo_data_uri_from_docx_bytes(docx_bytes)
            if photo_data_uri:
                cv_data["photo_url"] = photo_data_uri
        except Exception as e:
            logging.warning(f"Photo extraction failed: {e}")
    
    # Generate HTML
    try:
        html_content = render_html(cv_data, inline_css=True)
        
        return func.HttpResponse(
            body=html_content,
            mimetype="text/html",
            status_code=200
        )
    except Exception as e:
        logging.error(f"HTML generation failed: {e}")
        return func.HttpResponse(
            json.dumps({
                "error": "HTML generation failed",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="extract-photo", methods=["POST"])
def extract_photo(req: func.HttpRequest) -> func.HttpResponse:
    """
    Extract photo from DOCX (standalone endpoint)
    """
    logging.info('Extract photo requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    docx_base64 = req_body.get("docx_base64")
    if not docx_base64:
        return func.HttpResponse(
            json.dumps({"error": "Missing docx_base64 in request"}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        docx_bytes = base64.b64decode(docx_base64)
        photo_data_uri = extract_first_photo_data_uri_from_docx_bytes(docx_bytes)
        
        if not photo_data_uri:
            return func.HttpResponse(
                json.dumps({"error": "No photo found in DOCX"}),
                mimetype="application/json",
                status_code=404
            )
        
        return func.HttpResponse(
            json.dumps({"photo_data_uri": photo_data_uri}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Photo extraction failed: {e}")
        return func.HttpResponse(
            json.dumps({
                "error": "Photo extraction failed",
                "details": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="validate-cv", methods=["POST"])
def validate_cv_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Validate CV structure (standalone endpoint)
    """
    logging.info('Validate CV requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    cv_data = req_body.get("cv_data")
    if not cv_data:
        return func.HttpResponse(
            json.dumps({"error": "Missing cv_data in request"}),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize first
    cv_data = normalize_cv_data(cv_data)
    
    # Validate
    validation_result = validate_cv(cv_data)
    
    return func.HttpResponse(
        json.dumps({
            "is_valid": validation_result.is_valid,
            "errors": validation_result.errors,
            "warnings": validation_result.warnings,
            "estimated_pages": validation_result.estimated_pages
        }),
        mimetype="application/json",
        status_code=200
    )
