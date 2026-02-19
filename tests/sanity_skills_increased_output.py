#!/usr/bin/env python3
"""
Sanity test: Run skills proposal with increased output tokens and verify it returns 5-8 items per section.
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_store import CVSessionStore
from function_app import _openai_json_schema_call, _build_ai_system_prompt
from src.skills_unified_proposal import get_skills_unified_proposal_response_format, parse_skills_unified_proposal

def run_skills_sanity_test():
    """Test skills proposal with full candidate profile from opis do cv.txt"""
    
    skills_list = [
        "Design and deployment of AI-augmented productivity tools (GPT) for reporting and efficiency gains",
        "CAPEX/OPEX technical project management and budget control",
        "Technisches Projektmanagement (CAPEX/OPEX)",
        "Führung interdisziplinärer Teams",
        "Ursachenanalysen & Prozessverbesserungen (FMEA, 5 Why, PDCA)",
        "Baustellenmanagement (Strassenbau)",
        "Standardisierung & Optimierung auf datenbasierter Grundlage",
        "KI-gestützte Effizienz (GPT / Automatisierung / Reporting)",
    ]
    
    job_summary = """Project Manager - Technical Profile (M/F) – 100 % | Dietrich engineering consultants S.A. | Ecublens, Switzerland
Must-haves: Degree in Engineering (process, mechanical, or equivalent); Proven experience in process engineering or project management, ideally in a similar environment; Fluent in English; Proactive, dynamic, adaptable with strong initiative; Excellent organizational and problem-solving skills, able to perform under pressure; Strong communication skills and team player mindset
Tools/tech: P&ID; Functional Specifications; FAT (Factory Acceptance Test); SAT (Site Acceptance Test); Aseptic and containment filling lines; Isolator technologies; Powder transfer/handling/containment equipment
Keywords: project management; process engineering; design; manufacturing; budget management; client-facing; cross-functional collaboration; biotech; …"""
    
    ranking_notes = """GL: created construction company capable to deliver 30-40k EUR jobs, including public sector work. 
Expondo: technically solved 3-year-old quality issue - claims reduced by 70%, improved workflows.
Sumitomo: built quality team from scratch, IATF passed first try, multiple customer audits passed.
Sumitomo Process Improvement: international shop floor standardisation and KAIZEN implementation specialist."""
    
    skills_text = "\n".join([f"- {s}" for s in skills_list])
    
    user_text = (
        f"[JOB_SUMMARY]\n{job_summary}\n\n"
        f"[TAILORING_SUGGESTIONS]\n\n\n"
        f"[RANKING_NOTES]\n{ranking_notes}\n\n"
        f"[CANDIDATE_SKILLS]\n{skills_text}\n"
    )
    
    print("=" * 80)
    print("🧪 SANITY TEST: Skills Proposal with Increased Output Tokens")
    print("=" * 80)
    print(f"\n📊 Input:")
    print(f"   Skills provided: {len(skills_list)}")
    print(f"   User text length: {len(user_text)} chars")
    
    # Call OpenAI with increased max_output_tokens
    system_prompt = _build_ai_system_prompt(stage="it_ai_skills", target_language="en")
    
    print(f"\n🚀 Calling OpenAI...")
    print(f"   System prompt length: {len(system_prompt)} chars")
    print(f"   Max output tokens: 1800 (increased from 1200)")
    
    ok, parsed, err = _openai_json_schema_call(
        system_prompt=system_prompt,
        user_text=user_text,
        response_format=get_skills_unified_proposal_response_format(),
        max_output_tokens=1800,  # Increased limit
        stage="it_ai_skills",
    )
    
    if not ok:
        print(f"\n❌ FAILED: {err}")
        return False
    
    print(f"✅ API call succeeded")
    
    try:
        proposal = parse_skills_unified_proposal(parsed)
    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        return False
    
    print(f"\n📋 Results:")
    print(f"   IT & AI Skills: {len(proposal.it_ai_skills)} items")
    for i, skill in enumerate(proposal.it_ai_skills, 1):
        print(f"     {i}. {skill}")
    
    print(f"\n   Technical & Operational Skills: {len(proposal.technical_operational_skills)} items")
    for i, skill in enumerate(proposal.technical_operational_skills, 1):
        print(f"     {i}. {skill}")
    
    print(f"\n   Notes: {proposal.notes[:100]}...")
    
    # Validation
    it_ai_count = len(proposal.it_ai_skills)
    tech_op_count = len(proposal.technical_operational_skills)
    
    print(f"\n✅ Validation:")
    if 5 <= it_ai_count <= 8:
        print(f"   ✓ IT & AI Skills: {it_ai_count} items (target: 5-8)")
    else:
        print(f"   ✗ IT & AI Skills: {it_ai_count} items (expected 5-8)")
    
    if 5 <= tech_op_count <= 8:
        print(f"   ✓ Technical & Operational Skills: {tech_op_count} items (target: 5-8)")
    else:
        print(f"   ✗ Technical & Operational Skills: {tech_op_count} items (expected 5-8)")
    
    success = (5 <= it_ai_count <= 8) and (5 <= tech_op_count <= 8)
    
    print("\n" + "=" * 80)
    if success:
        print("✅ SANITY TEST PASSED: Skills proposal returns 5-8 items per section")
    else:
        print("❌ SANITY TEST FAILED: Skills proposal does not meet 5-8 target")
    print("=" * 80)
    
    return success

if __name__ == "__main__":
    success = run_skills_sanity_test()
    sys.exit(0 if success else 1)
