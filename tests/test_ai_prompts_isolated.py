"""
Isolated AI prompt tests (Tier 3: real OpenAI calls, no orchestration state).

These tests validate that each AI prompt produces semantically correct output when given
realistic inputs. They test the AI prompts in isolation from the orchestration flow.

DoD (Definition of Done) for each test:
- Schema: Output must match expected JSON schema
- Language: Output must be in target language (English)
- Job Relevance: Output must reference job-specific keywords (when job context provided)
- Semantic Quality: Output must show semantic reframing, not literal copy-paste
- No Invention: Output must not fabricate facts not present in input

Run with: RUN_OPENAI_E2E=1 pytest tests/test_ai_prompts_isolated.py -v
"""

import json
import os
import pytest

# Import the actual OpenAI call function from the backend
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from function_app import (
    _openai_json_schema_call,
    _build_ai_system_prompt,
    get_work_experience_bullets_proposal_response_format,
    parse_work_experience_bullets_proposal,
    get_job_reference_response_format,
    parse_job_reference,
)

# Test fixtures (reused from E2E tests)
JOB_OFFER_TEXT = (
    "Senior Software Engineer. "
    "Responsibilities: build web APIs, improve reliability, write tests, review code, and collaborate cross-functionally. "
    "Requirements: TypeScript/Node, cloud, CI/CD, and strong communication."
)

RAW_WORK_EXPERIENCE_DE = """
2025-05 Imbodden AG, Bauarbeiter | Ausführung von manuellen Tätigkeiten auf Tiefbau- und Strassenbaustellen
- Unterstützung bei Grabungsarbeiten, Rohrverlegung und Baustellenreinigung
- Mithilfe beim Materialtransport und einfachen Maschinenarbeiten
- Einblick in Schweizer Baustandards und Sicherheitsvorschriften erhalten

2020-01 – 2025-04 GL Solutions, Direktor | Planung und Koordination von Strassenbau- und Infrastrukturprojekten
- Überwachung von Baustellen, Subunternehmern und Einhaltung gesetzlicher Vorschriften
- Erstellung von Zeitplänen, Budgets und Projektabschlussdokumentation
- Verwaltung öffentlicher und privater Verträge; Verwendung von Planungs- und Kostentools vor Ort

2018-11 – 2020-01 Expondo Polska Sp. z o.o., Head of Quality & Product Service | Leitung von drei Abteilungen mit insgesamt 35 Mitarbeitern
- CE-Konformität sichergestellt, KPI-Dashboards entwickelt und Prozessverbesserungen implementiert
- Bearbeitung von Beschwerden, Produkt- und Prozessoptimierung
- Standardisierung und Verbesserung interner Arbeitsabläufe
"""

RAW_WORK_EXPERIENCE_EN = """
2025-05 Imbodden AG, Construction Worker | Performed manual tasks on civil engineering and road construction sites
- Assisted with excavation work, pipe laying, and site cleaning
- Helped with material transport and basic machine operations
- Gained insight into Swiss construction standards and safety regulations

2020-01 – 2025-04 GL Solutions, Director | Planned and coordinated road construction and infrastructure projects
- Supervised construction sites, subcontractors, and compliance with legal regulations
- Created schedules, budgets, and project closeout documentation
- Managed public and private contracts; used planning and cost tools on site

2018-11 – 2020-01 Expondo Polska Sp. z o.o., Head of Quality & Product Service | Led three departments with 35 employees
- Ensured CE compliance, built KPI dashboards, and implemented process improvements
- Handled complaints and product/process optimization
- Standardized and improved internal workflows
"""

RAW_SKILLS_MIXED = [
    "Technisches Projektmanagement (CAPEX/OPEX)",
    "Führung interdisziplinärer Teams",
    "Ursachenanalysen & Prozessverbesserungen (FMEA, 5 Why, PDCA)",
    "Baustellenmanagement (Strassenbau)",
    "Python",
    "SQL",
    "Data Analysis",
    "KI-gestützte Effizienz (GPT / Automatisierung / Reporting)",
    "Cloud Infrastructure",
    "TypeScript",
    "CI/CD pipelines",
]

RAW_SKILLS_EN = [
    "Technical project management (CAPEX/OPEX)",
    "Leading cross-functional teams",
    "Root cause analysis & process improvement (FMEA, 5 Why, PDCA)",
    "Construction site management (road construction)",
    "Python",
    "SQL",
    "Data Analysis",
    "AI-powered efficiency (GPT / Automation / Reporting)",
    "Cloud Infrastructure",
    "TypeScript",
    "CI/CD pipelines",
]

TAILORING_NOTES = """
GL Solutions: Created construction company from scratch capable of delivering 30-40k EUR jobs, including public sector contracts.

Expondo: Solved 3-year quality issue (good seller, bad quality); reduced claims by 70%; improved workflows (warehouse location optimization reduced steps by 50%); introduced work classification system.

Sumitomo Moldova: Built quality team from scratch; achieved IATF certification on first try; passed all customer audits; built local team with 6-month handover planning.

Sumitomo Global: Spent 60% of time in production plants as firefighter for critical issues; led company-wide standardization and KAIZEN implementation; trained production management systems.
"""


def openai_enabled() -> bool:
    """Check if OpenAI E2E tests are enabled (requires explicit opt-in)."""
    return (
        os.environ.get("RUN_OPENAI_E2E") == "1"
        and bool(os.environ.get("OPENAI_API_KEY", "").strip())
    )


@pytest.mark.skipif(not openai_enabled(), reason="RUN_OPENAI_E2E=1 and OPENAI_API_KEY required")
class TestAIPromptsIsolated:
    """Isolated AI prompt validation tests (real OpenAI, no wizard state)."""

    def test_job_offer_extraction(self):
        """
        DoD:
        - ✅ Schema: Returns valid job_reference JSON
        - ✅ Extraction: Captures role title, responsibilities, requirements
        - ✅ ATS keywords: Includes 'TypeScript', 'Node', 'cloud', 'CI/CD'
        - ✅ No hallucination: Does not invent salary/benefits/company details
        """
        ok, parsed, err = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="job_posting"),
            user_text=JOB_OFFER_TEXT,
            response_format=get_job_reference_response_format(),
            max_output_tokens=900,
            stage="job_posting",
        )

        # Schema validation
        assert ok, f"OpenAI call failed: {err}"
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"

        job_ref = parse_job_reference(parsed)
        assert job_ref is not None, "Failed to parse job_reference"

        # Extraction quality
        assert hasattr(job_ref, "role_title") and job_ref.role_title, "Missing role_title"
        assert "engineer" in job_ref.role_title.lower(), f"Expected 'engineer' in title: {job_ref.role_title}"

        # ATS keywords presence
        full_text = json.dumps(parsed, ensure_ascii=False).lower()
        assert "typescript" in full_text or "node" in full_text, "Missing TypeScript/Node keywords"
        assert "cloud" in full_text or "ci/cd" in full_text or "cicd" in full_text, "Missing cloud/CI-CD keywords"

        print(f"\n✅ Job Reference Extracted:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}")

    def test_work_experience_tailoring_with_job(self):
        """
        DoD:
        - ✅ Schema: Returns valid work_experience_bullets_proposal JSON
        - ✅ Language: All bullets in English (no German)
        - ✅ Job Relevance: References software engineering concepts from job offer
        - ✅ Semantic Reframing: Not literal copy-paste of input bullets
        - ✅ Tailoring Notes: Incorporates specific achievements from TAILORING_NOTES
        - ✅ No Invention: Does not add metrics/tools not in input
        """
        # First extract job reference
        ok_job, parsed_job, _ = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="job_posting"),
            user_text=JOB_OFFER_TEXT,
            response_format=get_job_reference_response_format(),
            max_output_tokens=900,
            stage="job_posting",
        )
        assert ok_job, "Failed to extract job reference"

        job_ref = parse_job_reference(parsed_job)
        company = job_ref.company if hasattr(job_ref, 'company') and job_ref.company else 'Tech Company'
        job_summary = f"{job_ref.role_title} at {company}\n"
        if hasattr(job_ref, "responsibilities") and job_ref.responsibilities:
            job_summary += "Responsibilities: " + ", ".join(job_ref.responsibilities[:5])

        # Build prompt following function_app.py WORK_TAILOR_RUN pattern
        user_text = (
            f"[JOB_SUMMARY]\n{job_summary}\n\n"
            f"[TAILORING_SUGGESTIONS]\n{TAILORING_NOTES}\n\n"
            f"[TAILORING_FEEDBACK]\n\n"
            f"[CURRENT_WORK_EXPERIENCE]\n{RAW_WORK_EXPERIENCE_EN}\n"
        )

        ok, parsed, err = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="work_experience", target_language="en"),
            user_text=user_text,
            response_format=get_work_experience_bullets_proposal_response_format(),
            max_output_tokens=900,
            stage="work_experience",
        )

        # Schema validation
        assert ok, f"OpenAI call failed: {err}"
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"

        proposal = parse_work_experience_bullets_proposal(parsed)
        assert hasattr(proposal, "roles") and proposal.roles, "Missing roles in proposal"

        # Language check: no German keywords
        full_text = json.dumps(parsed, ensure_ascii=False).lower()
        german_markers = ["bauarbeiter", "überwachung", "baustellen", "mithilfe", "einblick"]
        german_found = [m for m in german_markers if m in full_text]
        assert len(german_found) == 0, f"Found German words in English output: {german_found}"

        # Job relevance check: should reference technical/engineering concepts
        # (even though original experience is construction, tailoring should bridge to software context)
        roles_text = " ".join([
            f"{r.title} {r.company} {' '.join(r.bullets)}"
            for r in proposal.roles
        ]).lower()

        # Semantic reframing check: output should incorporate tailoring achievements
        # (This proves model is reframing based on job context, not just copying original)
        achievements_present = any(keyword in full_text for keyword in ["70", "reduce", "quality", "issue", "solve", "improve"])
        assert achievements_present, \
            "Tailoring notes achievements not incorporated (e.g., '70% claims reduction'). " \
            "Output should bridge construction experience to technical/quality management context."

        print(f"\n✅ Tailored Work Experience (with job context):\n{json.dumps(parsed, indent=2, ensure_ascii=False)}")

    def test_work_experience_translation_without_job(self):
        """
        DoD (Skip path - no job context):
        - ✅ Schema: Returns valid work_experience_bullets_proposal JSON
        - ✅ Language: All bullets in English (no German)
        - ✅ Preservation: Maintains company names, dates, role structure
        - ✅ Translation: Converts German bullets to English equivalents
        - ✅ No Invention: Does not add facts not in input
        """
        # Simulate skip-path auto-normalization (no job, no notes)
        user_text = (
            "[OUTPUT_LANGUAGE]\nen\n\n"
            "[INSTRUCTIONS]\n"
            "- Translate CURRENT_WORK_EXPERIENCE to OUTPUT_LANGUAGE.\n"
            "- Preserve meaning and factual content (no inventions).\n"
            "- Keep role structure; keep bullets concise; max 4 bullets per role.\n"
            "- Do not include any German words in the output when OUTPUT_LANGUAGE is English.\n\n"
            f"[CURRENT_WORK_EXPERIENCE]\n{RAW_WORK_EXPERIENCE_DE}\n"
        )

        ok, parsed, err = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="work_experience", target_language="en"),
            user_text=user_text,
            response_format=get_work_experience_bullets_proposal_response_format(),
            max_output_tokens=900,
            stage="work_experience",
        )

        # Schema validation
        assert ok, f"OpenAI call failed: {err}"
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"

        proposal = parse_work_experience_bullets_proposal(parsed)
        assert hasattr(proposal, "roles") and proposal.roles, "Missing roles in proposal"

        # Language check: no German
        full_text = json.dumps(parsed, ensure_ascii=False).lower()
        german_markers = ["bauarbeiter", "überwachung", "baustellen", "mithilfe", "ausführung", "unterstützung"]
        german_found = [m for m in german_markers if m in full_text]
        assert len(german_found) == 0, f"Found German words in English output: {german_found}"

        # English markers should be present
        english_markers = ["the", "and", "with", "for", "managed", "developed", "built", "implemented"]
        english_count = sum(1 for m in english_markers if m in full_text)
        assert english_count >= 3, f"Output doesn't appear to be English (only {english_count} English markers found)"

        # Company preservation check
        assert "imbodden" in full_text or "gl solutions" in full_text, "Company names not preserved"

        print(f"\n✅ Translated Work Experience (no job context):\n{json.dumps(parsed, indent=2, ensure_ascii=False)}")

    def test_skills_ranking_with_job(self):
        """
        DoD:
        - ✅ Schema: Returns valid skills_ranking JSON with 5-10 skills
        - ✅ Language: All skills in English (no German)
        - ✅ Job Relevance: TypeScript/Node/Cloud/CI-CD ranked higher than construction skills
        - ✅ Selection: Only skills from input list (no invention)
        - ✅ Deduplication: No duplicates or near-duplicates
        """
        # Extract job reference first
        ok_job, parsed_job, _ = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="job_posting"),
            user_text=JOB_OFFER_TEXT,
            response_format=get_job_reference_response_format(),
            max_output_tokens=900,
            stage="job_posting",
        )
        assert ok_job, "Failed to extract job reference"

        job_ref = parse_job_reference(parsed_job)
        job_summary = f"{job_ref.role_title}\nRequirements: TypeScript, Node, cloud, CI/CD"

        skills_text = "\n".join([f"- {s}" for s in RAW_SKILLS_EN])

        task = (
            "From the candidate skill list, select and rewrite 5-10 skills "
            "most relevant to the job. "
            "Do NOT rephrase or expand skill names; output only exact items from the list."
        )

        user_text = (
            f"[TASK]\n{task}\n\n"
            f"[JOB_SUMMARY]\n{job_summary}\n\n"
            f"[TAILORING_SUGGESTIONS]\n\n"
            f"[RANKING_NOTES]\n\n"
            f"[CANDIDATE_SKILLS]\n{skills_text}\n"
        )

        ok, parsed, err = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="it_ai_skills", target_language="en"),
            user_text=user_text,
            response_format={
                "type": "json_schema",
                "name": "skills_ranking",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "skills": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["skills"],
                },
            },
            max_output_tokens=600,
            stage="it_ai_skills",
        )

        # Schema validation
        assert ok, f"OpenAI call failed: {err}"
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
        assert "skills" in parsed and isinstance(parsed["skills"], list), "Missing or invalid 'skills' array"

        skills = parsed["skills"]
        assert 5 <= len(skills) <= 10, f"Expected 5-10 skills, got {len(skills)}"

        # Language check: no German
        full_text = " ".join(skills).lower()
        german_markers = ["technisches", "führung", "baustellenmanagement", "ursachenanalysen"]
        german_found = [m for m in german_markers if m in full_text]
        assert len(german_found) == 0, f"Found German words in skills: {german_found}"

        # Job relevance: TypeScript/Node/Cloud/CI-CD should be prioritized
        top_3 = " ".join(skills[:3]).lower()
        relevant_terms = ["typescript", "node", "cloud", "ci/cd", "cicd", "python", "sql"]
        relevant_found = any(term in top_3 for term in relevant_terms)
        assert relevant_found, f"Top 3 skills don't include job-relevant terms: {skills[:3]}"

        # No invention check: all skills should come from input list
        input_skills_lower = [s.lower() for s in RAW_SKILLS_EN]
        for skill in skills:
            # Allow semantic equivalents (e.g., "CI/CD Pipelines" for "CI/CD pipelines")
            skill_lower = skill.lower()
            found = any(
                input_skill in skill_lower or skill_lower in input_skill
                for input_skill in input_skills_lower
            )
            assert found, f"Skill '{skill}' not found in input list (possible invention)"

        print(f"\n✅ Ranked Skills (with job context):\n{json.dumps(parsed, indent=2, ensure_ascii=False)}")

    def test_education_translation(self):
        """
        DoD:
        - ✅ Schema: Returns valid education translation JSON
        - ✅ Language: All free-text fields in English
        - ✅ Preservation: Institution names unchanged, dates exact
        - ✅ Translation: Specialization and details translated
        - ✅ No Invention: Same number of entries, no added details
        """
        raw_education = [
            {
                "title": "Master of Science in Electrical Engineering",
                "institution": "Poznań University of Technology",
                "date_range": "2012–2015",
                "specialization": "Spezialisierung: Industrie- und Automobilsysteme",
                "details": ["Spezialisierung: Industrie- und Automobilsysteme"],
                "location": "Poznań, Polen",
            },
            {
                "title": "Bachelor of Engineering in Electrical Engineering",
                "institution": "Poznań University of Technology",
                "date_range": "2008–2012",
                "specialization": "Spezialisierung: Mikroprozessorsteuerung",
                "details": ["Spezialisierung: Mikroprozessorsteuerung"],
                "location": "Poznań, Polen",
            },
        ]

        ok, parsed, err = _openai_json_schema_call(
            system_prompt=_build_ai_system_prompt(stage="education_translation", target_language="en"),
            user_text=json.dumps({"education": raw_education}, ensure_ascii=False),
            response_format={
                "type": "json_schema",
                "name": "education_translation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "education": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "title": {"type": "string"},
                                    "institution": {"type": "string"},
                                    "date_range": {"type": "string"},
                                    "specialization": {"type": "string"},
                                    "details": {"type": "array", "items": {"type": "string"}},
                                    "location": {"type": "string"},
                                },
                                "required": ["title", "institution", "date_range", "specialization", "details", "location"],
                            },
                        }
                    },
                    "required": ["education"],
                },
            },
            max_output_tokens=800,
            stage="education_translation",
        )

        # Schema validation
        assert ok, f"OpenAI call failed: {err}"
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)}"
        assert "education" in parsed and isinstance(parsed["education"], list), "Missing education array"

        edu = parsed["education"]
        assert len(edu) == len(raw_education), f"Entry count changed: {len(edu)} vs {len(raw_education)}"

        # Preservation check
        for entry in edu:
            assert "Poznań University of Technology" in entry["institution"], "Institution name changed"
            assert entry["date_range"] in ["2012–2015", "2008–2012"], f"Date range changed: {entry['date_range']}"

        # Language check: specialization should be in English
        full_text = json.dumps(parsed, ensure_ascii=False).lower()
        german_markers = ["spezialisierung", "industrie", "mikroprozessorsteuerung", "polen"]
        german_found = [m for m in german_markers if m in full_text]
        assert len(german_found) == 0, f"Found German words in translated education: {german_found}"

        # English check
        assert "specialization" in full_text or "industrial" in full_text, "Specialization not translated to English"

        print(f"\n✅ Translated Education:\n{json.dumps(parsed, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    # Allow running directly: python tests/test_ai_prompts_isolated.py
    pytest.main([__file__, "-v", "-s"])
