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
from src.context_pack import build_context_pack


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
        # Graceful fallback: guide the model to include cv_data in next call
        return func.HttpResponse(
            json.dumps({
                "error": "cv_data is required",
                "guidance": "The cv_data parameter is missing or empty. You MUST include the complete CV JSON object (with full_name, email, phone, work_experience, education, etc.) that you presented to the user."
            }),
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
        # Graceful fallback: guide the model to include cv_data in next call
        return func.HttpResponse(
            json.dumps({
                "error": "cv_data is required",
                "guidance": "The cv_data parameter is missing or empty. You MUST include the complete CV JSON object (with full_name, email, phone, work_experience, education, etc.) that you presented to the user. Do not call this tool with only source_docx_base64 and language.",
                "required_fields": ["full_name", "email", "phone", "work_experience", "education"],
                "example_structure": {
                    "full_name": "John Doe",
                    "email": "john@example.com",
                    "phone": "+1234567890",
                    "work_experience": [{"date_range": "2020-2024", "employer": "Acme Corp", "title": "Engineer", "bullets": ["Achievement 1"]}],
                    "education": [{"date_range": "2016-2020", "institution": "University", "title": "Degree", "details": []}]
                }
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Unwrap double-wrapped cv_data (agent sometimes sends {"cv_data": {"cv_data": {...}}})
    if isinstance(cv_data, dict) and 'cv_data' in cv_data and not cv_data.get('full_name'):
        # If cv_data contains a nested cv_data key and lacks expected fields, unwrap it
        logging.info("Detected double-wrapped cv_data, unwrapping...")
        cv_data = cv_data['cv_data']
    
    # Log incoming data structure for debugging
    logging.info(f"CV data keys received: {list(cv_data.keys()) if isinstance(cv_data, dict) else 'not a dict'}")
    if isinstance(cv_data, dict):
        logging.info(f"Has full_name: {bool(cv_data.get('full_name'))}")
        logging.info(f"Has email: {bool(cv_data.get('email'))}")
        logging.info(f"Work experience count: {len(cv_data.get('work_experience', []))}")
        logging.info(f"Education count: {len(cv_data.get('education', []))}")
    
    # Pre-render validation: check for minimum viable content
    viability_issues = []
    if not cv_data.get('full_name'):
        viability_issues.append("full_name is required")
    if not cv_data.get('email'):
        viability_issues.append("email is required")
    if not cv_data.get('phone'):
        viability_issues.append("phone is required")
    if not cv_data.get('work_experience') or not isinstance(cv_data.get('work_experience'), list) or len(cv_data.get('work_experience', [])) == 0:
        viability_issues.append("At least one work_experience entry is required")
    if not cv_data.get('education') or not isinstance(cv_data.get('education'), list) or len(cv_data.get('education', [])) == 0:
        viability_issues.append("At least one education entry is required")
    
    if viability_issues:
        logging.warning(f"CV pre-validation failed: {viability_issues}")
        return func.HttpResponse(
            json.dumps({
                "error": "CV data incomplete",
                "issues": viability_issues,
                "guidance": "CV must include: full name, email, phone, at least one work experience entry, and at least one education entry."
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize CV data
    cv_data = normalize_cv_data(cv_data)
    logging.info(f"After normalization - work_experience: {len(cv_data.get('work_experience', []))}, education: {len(cv_data.get('education', []))}")
    
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
        debug_allow_pages = bool(req_body.get("debug_allow_pages"))
        logging.info(f"About to render PDF with cv_data: work_exp={len(cv_data.get('work_experience', []))}, edu={len(cv_data.get('education', []))}, name={bool(cv_data.get('full_name'))}")
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=not debug_allow_pages)
        logging.info(f"PDF rendered successfully: {len(pdf_bytes)} bytes")
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "pdf_base64": pdf_base64,
                "debug_allow_pages": debug_allow_pages,
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
        logging.error(f"CV data at failure: {json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k,v in cv_data.items()})}")
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
            "errors": [asdict(err) for err in validation_result.errors],
            "warnings": validation_result.warnings,
            "estimated_pages": validation_result.estimated_pages,
            "estimated_height_mm": validation_result.estimated_height_mm,
            "details": validation_result.details,
        }),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="generate-context-pack", methods=["POST"])
def generate_context_pack(req: func.HttpRequest) -> func.HttpResponse:
    """
    Build ContextPackV1 from provided CV JSON and optional job posting text.
    Returns JSON with the context pack.
    """
    logging.info('Generate Context Pack requested')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400,
        )

    cv_data = req_body.get("cv_data")
    if not cv_data:
        return func.HttpResponse(
            json.dumps({"error": "Missing cv_data in request"}),
            mimetype="application/json",
            status_code=400,
        )

    job_posting_text = req_body.get("job_posting_text")
    user_preferences = req_body.get("user_preferences") or {}
    max_pack_chars = req_body.get("max_pack_chars") or 12000

    try:
        pack = build_context_pack(
            cv_data=cv_data,
            job_posting_text=job_posting_text,
            user_preferences=user_preferences,
            max_pack_chars=max_pack_chars,
        )

        return func.HttpResponse(
            json.dumps(pack, ensure_ascii=False),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.error(f"Context pack generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Context pack generation failed", "details": str(e)}),
            mimetype="application/json",
            status_code=500,
        )
