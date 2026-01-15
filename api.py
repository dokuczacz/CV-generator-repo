"""
Simple Flask API for CV generation
Receives JSON with CV data, returns PDF file
"""

from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import io
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.render import render_pdf, render_html
from src.validator import validate_cv

app = Flask(__name__)
CORS(app)  # Enable CORS for GPT integration


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "CV Generator API",
        "version": "1.0",
        "endpoints": {
            "/health": "Health check",
            "/generate-cv": "POST - Generate CV PDF from JSON",
            "/preview-html": "POST - Preview CV as HTML"
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})


@app.route("/generate-cv", methods=["POST"])
def generate_cv():
    """
    Generate CV PDF from JSON data.
    
    Expected JSON fields:
    - full_name: str
    - address_lines: list[str]
    - phone: str
    - email: str
    - nationality: str
    - profile: str
    - work_experience: list[dict]
    - education: list[dict]
    - languages: list[str]
    - it_ai_skills: list[str]
    - trainings: list[str]
    - interests: str
    - data_privacy: str
    """
    try:
        cv_data = request.get_json()
        
        if not cv_data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        required_fields = ["full_name", "email"]
        missing = [f for f in required_fields if f not in cv_data]
        if missing:
            return jsonify({
                "error": "Missing required fields",
                "missing_fields": missing
            }), 400
        
        # CRITICAL: Validate content limits (2-page enforcement)
        validation_result = validate_cv(cv_data)
        
        if not validation_result.is_valid:
            # Build detailed error response
            error_details = []
            for err in validation_result.errors:
                error_details.append({
                    "field": err.field,
                    "current": err.current_value,
                    "limit": err.limit,
                    "excess": err.excess,
                    "message": err.message,
                    "suggestion": err.suggestion
                })
            
            return jsonify({
                "error": "CV validation failed - exceeds 2-page limit",
                "estimated_pages": validation_result.estimated_pages,
                "estimated_height_mm": validation_result.estimated_height_mm,
                "max_pages": 2.0,
                "validation_errors": error_details,
                "height_breakdown": validation_result.details,
                "instructions": (
                    "Your CV content exceeds the 2-page maximum for Swiss market standards. "
                    "Please reduce content according to the suggestions below. "
                    "Consider: removing oldest work experience, reducing bullet points, "
                    "or shortening descriptions."
                )
            }), 400
        
        # Log warnings if close to limit
        if validation_result.warnings:
            print(f"WARNING: {validation_result.warnings}")
        
        # Generate PDF
        pdf_bytes = render_pdf(cv_data)
        
        # Create in-memory file
        pdf_io = io.BytesIO(pdf_bytes)
        pdf_io.seek(0)
        
        # Return PDF file
        filename = f"{cv_data.get('full_name', 'CV').replace(' ', '_')}.pdf"
        
        return send_file(
            pdf_io,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({
            "error": "Failed to generate CV",
            "message": str(e)
        }), 500


@app.route("/preview-html", methods=["POST"])
def preview_html():
    """
    Generate CV HTML preview from JSON data.
    Returns HTML content for preview purposes.
    """
    try:
        cv_data = request.get_json()
        
        if not cv_data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Generate HTML
        html_content = render_html(cv_data, inline_css=True)
        
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
    except Exception as e:
        return jsonify({
            "error": "Failed to generate HTML",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
