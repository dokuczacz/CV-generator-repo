import json
from src.session_store import CVSessionStore
from function_app import format_job_reference_for_display, _escape_user_input_for_prompt

sid = "d74bfb01-10c0-4427-b9d5-beb39ace6666"
store = CVSessionStore()
sess = store.get_session(sid) or {}
meta = sess.get("metadata") if isinstance(sess.get("metadata"), dict) else {}
cv = sess.get("cv_data") if isinstance(sess.get("cv_data"), dict) else {}

job_ref = meta.get("job_reference") if isinstance(meta.get("job_reference"), dict) else None
job_summary = format_job_reference_for_display(job_ref) if job_ref else ""

tailoring = _escape_user_input_for_prompt(str(meta.get("work_tailoring_notes") or ""))
notes = _escape_user_input_for_prompt(str(meta.get("skills_ranking_notes") or ""))

skills_from_cv = cv.get("it_ai_skills") if isinstance(cv.get("it_ai_skills"), list) else []
skills_legacy_from_cv = cv.get("technical_operational_skills") if isinstance(cv.get("technical_operational_skills"), list) else []

dpu = meta.get("docx_prefill_unconfirmed") if isinstance(meta.get("docx_prefill_unconfirmed"), dict) else None
skills_from_docx = dpu.get("it_ai_skills") if isinstance(dpu, dict) and isinstance(dpu.get("it_ai_skills"), list) else []
skills_legacy_from_docx = dpu.get("technical_operational_skills") if isinstance(dpu, dict) and isinstance(dpu.get("technical_operational_skills"), list) else []

seen = set()
skills_list = []
for s in list(skills_from_cv) + list(skills_legacy_from_cv) + list(skills_from_docx) + list(skills_legacy_from_docx):
    s_str = str(s).strip()
    if s_str and s_str.lower() not in seen:
        seen.add(s_str.lower())
        skills_list.append(s_str)

skills_text = "\n".join([f"- {str(s).strip()}" for s in skills_list[:30] if str(s).strip()])

user_text = (
    f"[JOB_SUMMARY]\n{job_summary}\n\n"
    f"[CANDIDATE_PROFILE]\n{str(cv.get('profile') or '')}\n\n"
    f"[TAILORING_SUGGESTIONS]\n{tailoring}\n\n"
    f"[RANKING_NOTES]\n{notes}\n\n"
    f"[CANDIDATE_SKILLS]\n{skills_text}\n"
)

print("user_text_len:", len(user_text))
print("skills_list_count:", len(skills_list))
print("skills_list:", json.dumps(skills_list, ensure_ascii=False, indent=2))
print("\nuser_text:\n")
print(user_text)
