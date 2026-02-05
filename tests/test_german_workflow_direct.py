"""
Direct API test for German CV workflow (bypasses UI)
Tests the complete flow: upload CV -> select German -> generate CV + cover letter
"""
import requests
import json
import time
import os
import base64

BASE_URL = "http://localhost:3000"  # Next.js frontend (proxies to backend)
CV_PATH = r"C:\Users\Mariusz\OneDrive\Pulpit\Docs\CV\Lebenslauf_Mariusz_Horodecki_CH.docx"
JOB_TEXT = """
AI Consultant (m/w/d) - HICO Group AG
100% position seeking AI/ML expert with Swiss consulting experience.

Requirements:
- 5+ years experience in AI/ML consulting
- Python, LLMs, Cloud platforms (Azure, AWS)
- Strong communication skills in German and English
- Experience with enterprise AI implementations
"""

def test_german_cv_workflow():
    print("=" * 80)
    print("GERMAN CV WORKFLOW TEST (Direct API)")
    print("=" * 80)
    
    session_id = None
    
    # Step 1: Upload CV
    print("\n[1] Uploading CV...")
    with open(CV_PATH, 'rb') as f:
        docx_bytes = f.read()
        docx_base64 = base64.b64encode(docx_bytes).decode('utf-8')
    
    payload = {
        'message': '',
        'docx_base64': docx_base64,
        'session_id': '',
        'job_posting_url': 'https://www.jobs.ch/en/vacancies/detail/90a713e0-30da-4cd6-a3b9-f6beac01427a/',
       'job_posting_text': JOB_TEXT,
        'client_context': {
            'fast_path_profile': True
        }
    }
    
    resp = requests.post(f"{BASE_URL}/api/process-cv", json=payload, timeout=120)
    print(f"  HTTP Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"✗ Error: HTTP {resp.status_code}")
        print(f"  Response: {resp.text[:1000]}")
        return False
    
    result = resp.json()
    session_id = result.get('session_id')
    print(f"✓ Session created: {session_id}")
    print(f"  Stage: {result.get('stage')}")
    print(f"  UI Action: {result.get('ui_action', {}).get('title')}")
    
    # Step 2: Select German language
    print("\n[2] Selecting German language...")
    payload = {
        'session_id': session_id,
        'user_action': {'id': 'LANGUAGE_SELECT_DE'},
        'message': ''
    }
    resp = requests.post(f"{BASE_URL}/api/process-cv", json=payload, timeout=120)
    result = resp.json()
    print(f"✓ Language selected: DE")
    print(f"  Stage: {result.get('stage')}")
    print(f"  Response: {result.get('response', '')[:100]}...")
    
    # Step 3: Continue through wizard (auto-confirm stages)
    max_turns = 20
    turn = 0
    cv_generated = False
    cl_generated = False
    
    while turn < max_turns:
        turn += 1
        time.sleep(2)
        
        ui_action = result.get('ui_action')
        if not ui_action:
            print(f"\n[Turn {turn}] No more UI actions - workflow complete")
            break
        
        stage = result.get('stage', '').upper()
        actions = ui_action.get('actions', [])
        
        print(f"\n[Turn {turn}] Stage: {stage}")
        print(f"  Title: {ui_action.get('title')}")
        print(f"  Actions: {[a['id'] for a in actions]}")
        
        # Check for PDFs and save artifacts
        if result.get('pdf_base64'):
            filename = result.get('filename', 'output.pdf')
            output_dir = os.path.join(os.path.dirname(__file__), 'test-output', 'artifacts')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)
            pdf_bytes = base64.b64decode(result.get('pdf_base64'))
            with open(output_path, 'wb') as out_f:
                out_f.write(pdf_bytes)

            if 'cover' in filename.lower() or 'anschreiben' in filename.lower():
                cl_generated = True
                print(f"  ✓ COVER LETTER PDF GENERATED: {filename}")
            else:
                cv_generated = True
                print(f"  ✓ CV PDF GENERATED: {filename}")
            print(f"  ✓ Saved PDF artifact: {output_path}")
        
        # Auto-select primary action
        primary = next((a for a in actions if a.get('style') != 'secondary' and a.get('style') != 'tertiary'), None)
        if not primary:
            primary = actions[0] if actions else None
        
        if not primary:
            print("  ⚠ No actions available - stopping")
            break
        
        action_id = primary['id']
        print(f"  → Executing: {action_id}")
        
        payload = {
            'session_id': session_id,
            'user_action': {'id': action_id},
            'message': ''
        }
        resp = requests.post(f"{BASE_URL}/api/process-cv", json=payload, timeout=180)
        result = resp.json()
        
        if not result.get('success'):
            print(f"  ✗ Error: {result.get('error')}")
            break
    
    # Final summary
    print("\n" + "=" * 80)
    print("WORKFLOW COMPLETE")
    print("=" * 80)
    print(f"✓ Total turns: {turn}")
    print(f"✓ CV PDF generated: {'YES' if cv_generated else 'NO'}")
    print(f"✓ Cover letter PDF generated: {'YES' if cl_generated else 'NO'}")
    
    if cv_generated and cl_generated:
        print("\n✅ DoD MET: Both German CV and cover letter generated")
        return True
    else:
        print("\n❌ DoD NOT MET: Missing artifacts")
        return False

if __name__ == "__main__":
    try:
        success = test_german_cv_workflow()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
