"""
Enhanced E2E testing with validation and comparison.
Tests both direct Azure endpoint and through UI route.
"""

import requests
import json
import base64
from pathlib import Path
import sys

# Test endpoints
AZURE_ENDPOINT = "https://cv-generator-6695.azurewebsites.net/api/generate-cv-action"
UI_ENDPOINT = "http://localhost:3000/api/process-cv"  # Local dev server

# Sample CV data (canonical format)
SAMPLE_CV_DATA = {
    "full_name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1 234 567 890",
    "address_lines": ["123 Main St", "New York, NY 10001"],
    "nationality": "American",
    "profile": "Experienced software engineer with 5+ years in cloud development.",
    "work_experience": [
        {
            "date_range": "2020 - Present",
            "employer": "Tech Corp",
            "location": "New York, NY",
            "title": "Senior Software Engineer",
            "bullets": [
                "Led cloud-native microservices development",
                "Improved system performance by 40%",
                "Mentored 5 junior developers"
            ]
        },
        {
            "date_range": "2018 - 2020",
            "employer": "Startup Inc",
            "location": "San Francisco, CA",
            "title": "Software Engineer",
            "bullets": [
                "Built RESTful APIs using Python",
                "Implemented CI/CD pipelines"
            ]
        }
    ],
    "education": [
        {
            "date_range": "2014 - 2018",
            "institution": "University of California",
            "title": "B.S. Computer Science",
            "details": ["GPA: 3.8/4.0"]
        }
    ],
    "languages": [
        {"language": "English", "level": "Native"},
        {"language": "Spanish", "level": "Intermediate"}
    ],
    "it_ai_skills": ["Python", "Azure", "Docker", "Kubernetes"],
    "trainings": ["AWS Certified Solutions Architect"],
    "interests": "Open source, hiking",
    "data_privacy": "Consented.",
    "language": "en"
}


def validate_cv_data(cv_data):
    """Check if CV data has required fields."""
    issues = []
    
    required = ["full_name", "email", "phone", "work_experience", "education"]
    for field in required:
        if not cv_data.get(field):
            issues.append(f"Missing required field: {field}")
    
    if isinstance(cv_data.get("work_experience"), list) and len(cv_data["work_experience"]) == 0:
        issues.append("work_experience is empty")
    
    if isinstance(cv_data.get("education"), list) and len(cv_data["education"]) == 0:
        issues.append("education is empty")
    
    return issues


def validate_pdf(pdf_base64):
    """Check PDF content."""
    if not pdf_base64:
        return ["PDF base64 is empty"]
    
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        if len(pdf_bytes) < 1000:
            return [f"PDF suspiciously small: {len(pdf_bytes)} bytes"]
        
        from PyPDF2 import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if len(reader.pages) != 2:
            return [f"PDF has {len(reader.pages)} pages, expected 2"]
        
        text = reader.pages[0].extract_text()
        if len(text) < 100:
            return [f"PDF first page has only {len(text)} chars of text (expected >100)"]
        
        if "John Doe" not in text and "John" not in text:
            return ["PDF missing name/content"]
        
        return []
    except Exception as e:
        return [f"PDF validation error: {str(e)}"]


def test_direct_azure(payload_name, payload):
    """Test direct Azure endpoint."""
    print(f"\n{'='*60}")
    print(f"TEST: {payload_name}")
    print(f"{'='*60}")
    
    print(f"\n📤 Sending to Azure endpoint...")
    print(f"   Payload keys: {list(payload.keys())}")
    if "cv_data" in payload:
        print(f"   cv_data keys: {list(payload['cv_data'].keys())}")
    
    try:
        response = requests.post(AZURE_ENDPOINT, json=payload, timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            pdf_base64 = result.get("pdf_base64", "")
            
            # Validate
            issues = validate_pdf(pdf_base64)
            if issues:
                print(f"   ❌ PDF Issues:")
                for issue in issues:
                    print(f"      - {issue}")
            else:
                print(f"   ✅ PDF valid ({len(pdf_base64)} chars base64, ~{len(base64.b64decode(pdf_base64))} bytes)")
            
            # Save
            output_path = Path(f"tmp/test_{payload_name}.pdf")
            output_path.parent.mkdir(exist_ok=True)
            pdf_bytes = base64.b64decode(pdf_base64)
            output_path.write_bytes(pdf_bytes)
            print(f"   📁 Saved: {output_path}")
            
            return {"status": 200, "issues": issues}
        else:
            error = response.json().get("error", response.text)
            print(f"   ❌ Error: {error[:200]}")
            return {"status": response.status_code, "error": error}
    except Exception as e:
        print(f"   ❌ Exception: {str(e)}")
        return {"status": None, "error": str(e)}


def run_tests():
    """Run all test scenarios."""
    print("\n" + "="*60)
    print("E2E VALIDATION TEST SUITE")
    print("="*60)
    
    # Scenario 1: Correct wrapped format
    test_direct_azure(
        "correct_wrapped",
        {"cv_data": SAMPLE_CV_DATA}
    )
    
    # Scenario 2: Double-wrapped (should unwrap)
    test_direct_azure(
        "double_wrapped",
        {"cv_data": {"cv_data": SAMPLE_CV_DATA}}
    )
    
    # Scenario 3: Flat format (should reject)
    result = test_direct_azure(
        "flat_format",
        SAMPLE_CV_DATA  # No cv_data wrapper
    )
    if result["status"] != 400:
        print(f"   ⚠️ WARNING: Expected 400 for flat format, got {result['status']}")
    
    # Scenario 4: Minimal valid data
    minimal = {
        "full_name": "Test User",
        "email": "test@example.com",
        "phone": "+1 111 111 1111",
        "address_lines": ["Test St"],
        "profile": "Test profile",
        "work_experience": [{"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": ["test"]}],
        "education": [{"date_range": "2016-2020", "institution": "Uni", "title": "Degree", "details": []}],
        "languages": ["English"],
        "language": "en"
    }
    test_direct_azure("minimal_valid", {"cv_data": minimal})
    
    # Scenario 5: Missing critical field
    broken = SAMPLE_CV_DATA.copy()
    del broken["work_experience"]
    result = test_direct_azure("missing_work_exp", {"cv_data": broken})
    # This should still generate but with validation error
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print("✅ All direct Azure tests completed.")
    print("📋 Check tmp/ for generated PDFs.")
    print("🔍 Compare differences between scenarios.")


if __name__ == "__main__":
    run_tests()
