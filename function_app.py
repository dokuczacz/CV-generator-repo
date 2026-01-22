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
from src.docx_photo import extract_first_photo_data_uri_from_docx_bytes, extract_first_photo_from_docx_bytes
from src.blob_store import CVBlobStore, BlobPointer
from src.docx_prefill import prefill_cv_from_docx_bytes
from src.normalize import normalize_cv_data
from src.context_pack import build_context_pack
from src.schema_validator import (
    detect_schema_mismatch, 
    validate_canonical_schema,
    build_schema_error_response,
    log_schema_debug_info
)
from src.session_store import CVSessionStore


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
    
    # === PHASE 1: SCHEMA VALIDATION ===
    # Detect if agent sent wrong schema (personal_info, employment_history, etc.)
    log_schema_debug_info(cv_data, context="generate-cv-action")
    wrong_keys = detect_schema_mismatch(cv_data)
    
    if wrong_keys:
        logging.error(f"Schema validation failed: wrong keys {wrong_keys}")
        return func.HttpResponse(
            json.dumps(build_schema_error_response(cv_data)),
            mimetype="application/json",
            status_code=400
        )
    
    # Unwrap double-wrapped cv_data (agent sometimes sends {"cv_data": {"cv_data": {...}}})
    if isinstance(cv_data, dict) and 'cv_data' in cv_data and not cv_data.get('full_name'):
        # If cv_data contains a nested cv_data key and lacks expected fields, unwrap it
        logging.info("Detected double-wrapped cv_data, unwrapping...")
        cv_data = cv_data['cv_data']
        # Re-validate after unwrapping
        log_schema_debug_info(cv_data, context="after unwrap")
    
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


# ============================================================================
# PHASE 2: SESSION-BASED ENDPOINTS
# ============================================================================

@app.route(route="extract-and-store-cv", methods=["POST"])
def extract_and_store_cv(req: func.HttpRequest) -> func.HttpResponse:
    """
    Extract CV data from DOCX and store in session
    
    This endpoint:
    1. Receives DOCX file (base64)
    2. Extracts CV data (using GPT or parsing logic - placeholder for now)
    3. Stores in Azure Table Storage
    4. Returns session_id for subsequent operations
    
    Request:
        {
            "docx_base64": "base64-encoded DOCX",
            "language": "en|de|pl",
            "extract_photo": true|false
        }
    
    Response:
        {
            "session_id": "uuid",
            "cv_data_summary": {...},
            "photo_extracted": true|false,
            "expires_at": "ISO timestamp"
        }
    """
    logging.info('Extract and store CV requested')
    
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
            json.dumps({"error": "docx_base64 is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    language = req_body.get("language", "en")
    extract_photo_flag = req_body.get("extract_photo", True)
    job_posting_url = (req_body.get("job_posting_url") or "").strip() or None
    job_posting_text = (req_body.get("job_posting_text") or "").strip() or None
    
    try:
        docx_bytes = base64.b64decode(docx_base64)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": "Invalid base64 encoding", "details": str(e)}),
            mimetype="application/json",
            status_code=400
        )
    
    # Extract photo if requested (store in Blob; do not store base64 in Table Storage)
    extracted_photo = None
    photo_extracted = False
    photo_storage = "none"
    photo_omitted_reason = None
    if extract_photo_flag:
        try:
            extracted_photo = extract_first_photo_from_docx_bytes(docx_bytes)
            photo_extracted = bool(extracted_photo)
            logging.info(f"Photo extraction: {'success' if extracted_photo else 'no photo found'}")
        except Exception as e:
            photo_omitted_reason = f"photo_extraction_failed: {e}"
            logging.warning(f"Photo extraction failed: {e}")
    
    # Best-effort extraction of basic CV fields from DOCX (no OpenAI call)
    prefill = prefill_cv_from_docx_bytes(docx_bytes)

    # Minimal structure; agent can fill/adjust the rest (but avoid empty required arrays when possible)
    cv_data = {
        "full_name": prefill.get("full_name", "") or "",
        "email": prefill.get("email", "") or "",
        "phone": prefill.get("phone", "") or "",
        "address_lines": prefill.get("address_lines", []) or [],
        "photo_url": "",
        "birth_date": "",
        "nationality": "",
        "profile": prefill.get("profile", "") or "",
        "work_experience": prefill.get("work_experience", []) or [],
        "education": prefill.get("education", []) or [],
        "it_ai_skills": prefill.get("it_ai_skills", []) or [],
        "languages": prefill.get("languages", []) or [],
        "certifications": [],
        "interests": prefill.get("interests", "") or "",
        "further_experience": prefill.get("further_experience", []) or [],
        "references": "",
        "language": language
    }
    
    # Store in session
    try:
        store = CVSessionStore()
        metadata = {
            "language": language,
            "source_file": "uploaded.docx",
            "extraction_method": "docx_prefill_v1"
        }
        if job_posting_url:
            metadata["job_posting_url"] = job_posting_url
        if job_posting_text:
            # Keep bounded to avoid Table Storage bloat; UI already bounds to 20k as well.
            metadata["job_posting_text"] = job_posting_text[:20000]
        session_id = store.create_session(cv_data, metadata)
    except Exception as e:
        logging.error(f"Session creation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to create session", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    # Store extracted photo in Blob (if any) and record a pointer in session metadata
    if extracted_photo and session_id:
        try:
            blob_store = CVBlobStore()
            ext = "jpg" if extracted_photo.mime == "image/jpeg" else "png" if extracted_photo.mime == "image/png" else "bin"
            blob_name = f"sessions/{session_id}/photo.{ext}"
            ptr = blob_store.upload_bytes(blob_name=blob_name, data=extracted_photo.data, content_type=extracted_photo.mime)
            metadata = dict(metadata)
            metadata["photo_blob"] = {"container": ptr.container, "blob_name": ptr.blob_name, "content_type": ptr.content_type}
            store.update_session(session_id, cv_data, metadata)
            photo_storage = "blob"
        except Exception as e:
            photo_storage = "none"
            photo_omitted_reason = f"photo_blob_store_failed: {e}"
            logging.warning(f"Photo blob storage failed: {e}")
    elif extract_photo_flag and not photo_extracted:
        photo_omitted_reason = photo_omitted_reason or "no_photo_found_in_docx"

    # Build summary for response (avoid sending full data back)
    summary = {
        "has_photo": photo_extracted,
        "fields_populated": [k for k, v in cv_data.items() if v],
        "fields_empty": [k for k, v in cv_data.items() if not v]
    }
    
    session = store.get_session(session_id)
    
    return func.HttpResponse(
        json.dumps({
            "success": True,
            "session_id": session_id,
            "cv_data_summary": summary,
            "photo_extracted": photo_extracted,
            "photo_storage": photo_storage,
            "photo_omitted_reason": photo_omitted_reason,
            "expires_at": session["expires_at"]
        }),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="get-cv-session", methods=["GET", "POST"])
def get_cv_session(req: func.HttpRequest) -> func.HttpResponse:
    """
    Retrieve CV data from session
    
    Request (POST):
        {"session_id": "uuid"}
    
    Or GET with query param:
        ?session_id=uuid
    
    Response:
        {
            "cv_data": {...},
            "metadata": {...},
            "session_id": "uuid",
            "expires_at": "ISO timestamp"
        }
    """
    logging.info('Get CV session requested')
    
    if req.method == "GET":
        session_id = req.params.get("session_id")
    else:
        try:
            req_body = req.get_json()
            session_id = req_body.get("session_id")
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON"}),
                mimetype="application/json",
                status_code=400
            )
    
    if not session_id:
        return func.HttpResponse(
            json.dumps({"error": "session_id is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        logging.error(f"Session retrieval failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    if not session:
        return func.HttpResponse(
            json.dumps({"error": "Session not found or expired"}),
            mimetype="application/json",
            status_code=404
        )
    
    return func.HttpResponse(
        json.dumps({
            "success": True,
            "session_id": session["session_id"],
            "cv_data": session["cv_data"],
            "metadata": session["metadata"],
            "expires_at": session["expires_at"]
        }),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="update-cv-field", methods=["POST"])
def update_cv_field(req: func.HttpRequest) -> func.HttpResponse:
    """
    Update specific field in CV session
    
    Request:
        {
            "session_id": "uuid",
            "field_path": "full_name" or "work_experience[0].employer",
            "value": "new value"
        }
    
    Response:
        {
            "success": true,
            "session_id": "uuid",
            "field_updated": "field_path"
        }
    """
    logging.info('Update CV field requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    session_id = req_body.get("session_id")
    field_path = req_body.get("field_path")
    value = req_body.get("value")
    
    if not session_id or not field_path:
        return func.HttpResponse(
            json.dumps({"error": "session_id and field_path are required"}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        store = CVSessionStore()
        updated = store.update_field(session_id, field_path, value)
    except Exception as e:
        logging.error(f"Field update failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to update field", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    if not updated:
        return func.HttpResponse(
            json.dumps({"error": "Session not found"}),
            mimetype="application/json",
            status_code=404
        )
    
    return func.HttpResponse(
        json.dumps({
            "success": True,
            "session_id": session_id,
            "field_updated": field_path
        }),
        mimetype="application/json",
        status_code=200
    )


@app.route(route="generate-cv-from-session", methods=["POST"])
def generate_cv_from_session(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate PDF from session data
    
    Request:
        {
            "session_id": "uuid",
            "language": "en|de|pl" (optional, uses session metadata if not provided)
        }
    
    Response:
        {
            "success": true,
            "pdf_base64": "...",
            "validation": {...}
        }
    """
    logging.info('Generate CV from session requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    session_id = req_body.get("session_id")
    if not session_id:
        return func.HttpResponse(
            json.dumps({"error": "session_id is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    try:
        store = CVSessionStore()
        session = store.get_session(session_id)
    except Exception as e:
        logging.error(f"Session retrieval failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
    
    if not session:
        return func.HttpResponse(
            json.dumps({"error": "Session not found or expired"}),
            mimetype="application/json",
            status_code=404
        )
    
    cv_data = session["cv_data"]
    language = req_body.get("language") or session["metadata"].get("language", "en")

    # If photo stored in Blob, inject it into cv_data as data URI at render time.
    # (We keep Table Storage session lean; the HTML template expects photo_url.)
    try:
        metadata = session.get("metadata") or {}
        photo_blob = metadata.get("photo_blob") if isinstance(metadata, dict) else None
        if photo_blob and not cv_data.get("photo_url"):
            ptr = BlobPointer(
                container=photo_blob.get("container", ""),
                blob_name=photo_blob.get("blob_name", ""),
                content_type=photo_blob.get("content_type", "application/octet-stream"),
            )
            if ptr.container and ptr.blob_name:
                data = CVBlobStore(container=ptr.container).download_bytes(ptr)
                b64 = base64.b64encode(data).decode("ascii")
                cv_data = dict(cv_data)
                cv_data["photo_url"] = f"data:{ptr.content_type};base64,{b64}"
    except Exception as e:
        logging.warning(f"Failed to inject photo from blob for session {session_id}: {e}")
    
    # Schema validation
    log_schema_debug_info(cv_data, context="generate-from-session")
    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    
    if not is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "CV data validation failed",
                "validation_errors": errors,
                "guidance": "Use update-cv-field to fix missing or invalid fields"
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Normalize and validate
    cv_data = normalize_cv_data(cv_data)
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
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        logging.info(f"PDF generated from session {session_id}: {len(pdf_bytes)} bytes")
        
        # Return raw binary PDF, not base64-encoded JSON
        return func.HttpResponse(
            body=pdf_bytes,
            mimetype="application/pdf",
            status_code=200
        )
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "PDF generation failed", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )


# ============================================================================
# PHASE 3: ORCHESTRATION ENDPOINT
# ============================================================================

@app.route(route="process-cv-orchestrated", methods=["POST"])
def process_cv_orchestrated(req: func.HttpRequest) -> func.HttpResponse:
    """
    Orchestrated CV processing - single endpoint for full workflow
    
    This endpoint handles the complete CV processing pipeline:
    1. Extract CV data from DOCX (or use existing session)
    2. Apply user edits if provided
    3. Validate CV data
    4. Generate PDF
    
    Request:
        {
            "session_id": "uuid" (optional - reuse existing session),
            "docx_base64": "base64" (required if no session_id),
            "language": "en|de|pl" (optional, default: en),
            "edits": [
                {"field_path": "full_name", "value": "John Doe"},
                {"field_path": "work_experience[0].employer", "value": "Acme"}
            ] (optional),
            "extract_photo": true|false (optional, default: true)
        }
    
    Response:
        {
            "success": true,
            "session_id": "uuid",
            "pdf_base64": "...",
            "validation": {...},
            "cv_data_summary": {...}
        }
    """
    logging.info('Orchestrated CV processing requested')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    session_id = req_body.get("session_id")
    docx_base64 = req_body.get("docx_base64")
    language = req_body.get("language", "en")
    edits = req_body.get("edits", [])
    extract_photo_flag = req_body.get("extract_photo", True)
    job_posting_url = (req_body.get("job_posting_url") or "").strip() or None
    job_posting_text = (req_body.get("job_posting_text") or "").strip() or None
    
    store = CVSessionStore()
    
    # Step 1: Get or create session
    if session_id:
        logging.info(f"Using existing session: {session_id}")
        try:
            session = store.get_session(session_id)
            if not session:
                return func.HttpResponse(
                    json.dumps({"error": "Session not found or expired"}),
                    mimetype="application/json",
                    status_code=404
                )
            cv_data = session["cv_data"]
            metadata = session.get("metadata") or {}
            if job_posting_url:
                metadata["job_posting_url"] = job_posting_url
            if job_posting_text:
                metadata["job_posting_text"] = job_posting_text[:20000]
            if job_posting_url or job_posting_text:
                store.update_session(session_id, cv_data, metadata)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Failed to retrieve session", "details": str(e)}),
                mimetype="application/json",
                status_code=500
            )
    elif docx_base64:
        logging.info("Creating new session from DOCX")
        try:
            docx_bytes = base64.b64decode(docx_base64)
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Invalid base64 encoding", "details": str(e)}),
                mimetype="application/json",
                status_code=400
            )
        
        # Extract photo (store in Blob after session is created)
        extracted_photo = None
        photo_extracted = False
        photo_storage = "none"
        photo_omitted_reason = None
        if extract_photo_flag:
            try:
                extracted_photo = extract_first_photo_from_docx_bytes(docx_bytes)
                photo_extracted = bool(extracted_photo)
            except Exception as e:
                photo_omitted_reason = f"photo_extraction_failed: {e}"
                logging.warning(f"Photo extraction failed: {e}")
        
        # Best-effort extraction of basic CV fields (no OpenAI call)
        prefill = prefill_cv_from_docx_bytes(docx_bytes)

        # Create minimal CV data (agent will populate via edits)
        cv_data = {
            "full_name": prefill.get("full_name", "") or "",
            "email": prefill.get("email", "") or "",
            "phone": prefill.get("phone", "") or "",
            "address_lines": prefill.get("address_lines", []) or [],
            "photo_url": "",
            "birth_date": "",
            "nationality": "",
            "profile": prefill.get("profile", "") or "",
            "work_experience": prefill.get("work_experience", []) or [],
            "education": prefill.get("education", []) or [],
            "it_ai_skills": prefill.get("it_ai_skills", []) or [],
            "languages": prefill.get("languages", []) or [],
            "certifications": [],
            "interests": prefill.get("interests", "") or "",
            "further_experience": prefill.get("further_experience", []) or [],
            "references": "",
            "language": language
        }
        
        try:
            metadata = {"language": language, "source_file": "uploaded.docx"}
            if job_posting_url:
                metadata["job_posting_url"] = job_posting_url
            if job_posting_text:
                metadata["job_posting_text"] = job_posting_text[:20000]
            session_id = store.create_session(cv_data, metadata)
            logging.info(f"Created session: {session_id}")
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": "Failed to create session", "details": str(e)}),
                mimetype="application/json",
                status_code=500
            )

        # Store photo in Blob and persist pointer in metadata
        if extracted_photo and session_id:
            try:
                blob_store = CVBlobStore()
                ext = "jpg" if extracted_photo.mime == "image/jpeg" else "png" if extracted_photo.mime == "image/png" else "bin"
                blob_name = f"sessions/{session_id}/photo.{ext}"
                ptr = blob_store.upload_bytes(blob_name=blob_name, data=extracted_photo.data, content_type=extracted_photo.mime)
                metadata = dict(metadata)
                metadata["photo_blob"] = {"container": ptr.container, "blob_name": ptr.blob_name, "content_type": ptr.content_type}
                store.update_session(session_id, cv_data, metadata)
                photo_storage = "blob"
            except Exception as e:
                photo_storage = "none"
                photo_omitted_reason = f"photo_blob_store_failed: {e}"
                logging.warning(f"Photo blob storage failed: {e}")
        elif extract_photo_flag and not photo_extracted:
            photo_omitted_reason = photo_omitted_reason or "no_photo_found_in_docx"
    else:
        return func.HttpResponse(
            json.dumps({"error": "Either session_id or docx_base64 is required"}),
            mimetype="application/json",
            status_code=400
        )
    
    # Step 2: Apply edits if provided
    if edits:
        logging.info(f"Applying {len(edits)} edits to session {session_id}")
        for edit in edits:
            field_path = edit.get("field_path")
            value = edit.get("value")
            if field_path:
                try:
                    store.update_field(session_id, field_path, value)
                except Exception as e:
                    logging.warning(f"Failed to apply edit to {field_path}: {e}")
        
        # Refresh cv_data after edits
        session = store.get_session(session_id)
        cv_data = session["cv_data"]
    
    # Step 3: Validate
    log_schema_debug_info(cv_data, context="orchestrated")
    is_valid, errors = validate_canonical_schema(cv_data, strict=True)
    
    if not is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "CV data validation failed",
                "validation_errors": errors,
                "session_id": session_id,
                "guidance": "Provide edits array to populate missing fields"
            }),
            mimetype="application/json",
            status_code=400
        )
    
    cv_data = normalize_cv_data(cv_data)
    validation_result = validate_cv(cv_data)
    
    if not validation_result.is_valid:
        return func.HttpResponse(
            json.dumps({
                "error": "Validation failed",
                "validation": _serialize_validation_result(validation_result),
                "session_id": session_id
            }),
            mimetype="application/json",
            status_code=400
        )
    
    # Step 4: Generate PDF
    try:
        pdf_bytes = render_pdf(cv_data, enforce_two_pages=True)
        logging.info(f"Orchestrated: Generated PDF ({len(pdf_bytes)} bytes) for session {session_id}")
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        
        summary = {
            "has_photo": bool(cv_data.get("photo_url")),
            "work_experience_count": len(cv_data.get("work_experience", [])),
            "education_count": len(cv_data.get("education", [])),
            "languages": cv_data.get("languages", [])
        }
        
        return func.HttpResponse(
            json.dumps({
                "success": True,
                "session_id": session_id,
                "pdf_base64": pdf_base64,
                "validation": _serialize_validation_result(validation_result),
                "cv_data_summary": summary
            }),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Orchestrated: PDF generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "PDF generation failed", "details": str(e), "session_id": session_id}),
            mimetype="application/json",
            status_code=500
        )


@app.route(route="cleanup-expired-sessions", methods=["POST"])
def cleanup_expired_sessions(req: func.HttpRequest) -> func.HttpResponse:
    """
    Cleanup expired sessions (scheduled task or manual trigger)
    
    Response:
        {"deleted_count": 5}
    """
    logging.info('Cleanup expired sessions requested')
    
    try:
        store = CVSessionStore()
        deleted = store.cleanup_expired()
        
        return func.HttpResponse(
            json.dumps({"deleted_count": deleted}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Cleanup failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Cleanup failed", "details": str(e)}),
            mimetype="application/json",
            status_code=500
        )
