#!/usr/bin/env python3
"""
Diagnose what actually reached OpenAI by fetching Response object via response_id.
Uses OpenAI Responses API to retrieve full request context + output.

Usage:
  python scripts/diagnose_response_id.py <response_id>
  Example: python scripts/diagnose_response_id.py resp_08e9b0bda143faee006977c965a4f881a39c4ca3d2961346df
"""

import os
import sys
import json
import requests

def diagnose_response(response_id: str):
    """Fetch response object and show what reached the model."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"Fetching Response ID: {response_id}")
    print(f"{'='*80}\n")
    
    try:
        # Fetch the response object via REST API
        url = f"https://api.openai.com/v1/responses/{response_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        resp = response.json()
        
        # Display key fields
        print(f"STATUS: {resp.get('status')}")
        print(f"MODEL: {resp.get('model')}")
        print(f"CREATED AT: {resp.get('created_at')}")
        print(f"COMPLETED AT: {resp.get('completed_at')}\n")
        
        # Instructions (developer message)
        instructions = resp.get('instructions')
        if instructions:
            print(f"INSTRUCTIONS (Developer Role):")
            print(f"  Type: {type(instructions)}")
            if isinstance(instructions, str):
                # Truncate long instructions
                inst_display = instructions[:500] + "..." if len(instructions) > 500 else instructions
                print(f"  Content:\n    {inst_display}\n")
            else:
                print(f"  {json.dumps(instructions, indent=2)}\n")
        else:
            print("INSTRUCTIONS: (none)\n")
        
        # Show output (what the model sent back)
        print(f"OUTPUT (model's response):")
        output = resp.get('output', [])
        if output:
            for i, item in enumerate(output):
                print(f"\n  [{i}] Type: {item.get('type', 'unknown')}")
                if 'role' in item:
                    print(f"      Role: {item['role']}")
                if 'content' in item:
                    content = item['content']
                    if isinstance(content, list):
                        for j, c in enumerate(content):
                            print(f"      Content[{j}] Type: {c.get('type')}")
                            if 'text' in c:
                                text_display = c['text'][:300] + "..." if len(c['text']) > 300 else c['text']
                                print(f"      Content[{j}] Text:\n        {text_display}")
        else:
            print("  (no output items)")
        
        # Show usage
        usage = resp.get('usage')
        if usage:
            print(f"\nUSAGE:")
            print(f"  Input tokens: {usage.get('input_tokens')}")
            print(f"  Output tokens: {usage.get('output_tokens')}")
            print(f"  Total tokens: {usage.get('total_tokens')}\n")
        
        # Also fetch input_items (what was sent to the model)
        try:
            ii_url = f"https://api.openai.com/v1/responses/{response_id}/input_items"
            ii_resp = requests.get(ii_url, headers=headers)
            ii_resp.raise_for_status()
            ii = ii_resp.json()
            print(f"INPUT ITEMS (source context sent to model):")
            data = ii.get("data") or []
            if data:
                for i, item in enumerate(data):
                    itype = item.get("type")
                    role = item.get("role")
                    print(f"  [{i}] type={itype} role={role}")
                    content = item.get("content")
                    if isinstance(content, list):
                        for j, c in enumerate(content):
                            ctype = c.get("type")
                            txt = c.get("text")
                            if isinstance(txt, str):
                                txt_disp = txt[:300] + "..." if len(txt) > 300 else txt
                                print(f"      content[{j}] type={ctype} text=\n        {txt_disp}")
                            else:
                                print(f"      content[{j}] type={ctype}")
            else:
                print("  (no input_items returned)")
        except Exception as e:
            print(f"WARNING: Failed to fetch input_items: {e}")

        print(f"{'='*80}")
        print("ANALYSIS COMPLETE")
        print(f"{'='*80}\n")
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    response_id = sys.argv[1]
    diagnose_response(response_id)
