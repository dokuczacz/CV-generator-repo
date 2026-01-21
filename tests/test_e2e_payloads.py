"""
End-to-end testing for generate-cv-action endpoint with different payload formats.
Tests the unwrap logic for double-wrapped cv_data.
"""

import requests
import json
import base64
from pathlib import Path

# Azure endpoint
ENDPOINT = "https://cv-generator-6695.azurewebsites.net/api/generate-cv-action"

# Test CV data
SAMPLE_CV_DATA = {
    "full_name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1 234 567 890",
    "address_lines": ["123 Main St", "New York, NY 10001"],
    "nationality": "American",
    "profile": "Experienced software engineer with 5+ years in cloud development and AI/ML systems.",
    "work_experience": [
        {
            "date_range": "2020 - Present",
            "employer": "Tech Corp",
            "location": "New York, NY",
            "title": "Senior Software Engineer",
            "bullets": [
                "Led development of cloud-native microservices",
                "Improved system performance by 40%",
                "Mentored team of 5 junior developers"
            ]
        },
        {
            "date_range": "2018 - 2020",
            "employer": "Startup Inc",
            "location": "San Francisco, CA",
            "title": "Software Engineer",
            "bullets": [
                "Built RESTful APIs using Python and Flask",
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
    "it_ai_skills": ["Python", "Azure", "Docker", "Kubernetes", "Machine Learning"],
    "trainings": ["AWS Certified Solutions Architect"],
    "interests": "Open source, hiking, photography",
    "data_privacy": "I consent to processing of my personal data.",
    "language": "en"
}


def test_correct_wrapped():
    """Test 1: Correct wrapped format (expected from schema)"""
    print("\n=== Test 1: Correct Wrapped Format ===")
    payload = {
        "cv_data": SAMPLE_CV_DATA
    }
    
    response = requests.post(ENDPOINT, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        pdf_base64 = result.get("pdf_base64", "")
        print(f"PDF size: {len(pdf_base64)} chars (base64)")
        
        # Save PDF
        pdf_bytes = base64.b64decode(pdf_base64)
        output_path = Path("tmp/test_correct_wrapped.pdf")
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        print(f"✅ Saved: {output_path} ({len(pdf_bytes)} bytes)")
    else:
        print(f"❌ Error: {response.text}")


def test_double_wrapped():
    """Test 2: Double-wrapped format (agent mistake, should be fixed by unwrap logic)"""
    print("\n=== Test 2: Double-Wrapped Format (should unwrap) ===")
    payload = {
        "cv_data": {
            "cv_data": SAMPLE_CV_DATA
        }
    }
    
    response = requests.post(ENDPOINT, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        pdf_base64 = result.get("pdf_base64", "")
        print(f"PDF size: {len(pdf_base64)} chars (base64)")
        
        # Save PDF
        pdf_bytes = base64.b64decode(pdf_base64)
        output_path = Path("tmp/test_double_wrapped.pdf")
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        print(f"✅ Saved: {output_path} ({len(pdf_bytes)} bytes)")
    else:
        print(f"❌ Error: {response.text}")


def test_flat_format():
    """Test 3: Flat format (wrong, should be rejected)"""
    print("\n=== Test 3: Flat Format (should reject) ===")
    payload = SAMPLE_CV_DATA  # No cv_data wrapper
    
    response = requests.post(ENDPOINT, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 400:
        print(f"✅ Correctly rejected: {response.json().get('error')}")
    else:
        print(f"❌ Unexpected response: {response.text}")


def test_missing_cv_data():
    """Test 4: Missing cv_data (should return guidance)"""
    print("\n=== Test 4: Missing cv_data (should return guidance) ===")
    payload = {
        "source_docx_base64": "dummy",
        "language": "en"
    }
    
    response = requests.post(ENDPOINT, json=payload)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 400:
        result = response.json()
        print(f"✅ Guidance: {result.get('guidance')[:100]}...")
    else:
        print(f"❌ Unexpected response: {response.text}")


if __name__ == "__main__":
    print("E2E Payload Testing for generate-cv-action")
    print("=" * 50)
    
    # Wait for deployment
    print("\nWaiting 10 seconds for Azure deployment to complete...")
    import time
    time.sleep(10)
    
    # Run tests
    test_correct_wrapped()
    test_double_wrapped()
    test_flat_format()
    test_missing_cv_data()
    
    print("\n" + "=" * 50)
    print("Testing complete. Check tmp/ for generated PDFs.")
