#!/usr/bin/env python3
"""
Analyze Azure Functions logs to diagnose stage/tool issues.

Usage:
    python scripts/analyze_func_log.py tmp/logs/func_TIMESTAMP.log
"""
import json
import re
import sys
from pathlib import Path


def parse_func_log(log_path: Path) -> dict:
    """Parse key events from Azure Functions log."""
    if not log_path.exists():
        return {"error": f"Log file not found: {log_path}"}
    
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    
    # Extract session ID
    session_match = re.search(r"Created session ([a-f0-9-]+)", text)
    session_id = session_match.group(1) if session_match else None
    
    # Extract all trace lines
    traces = []
    for line in text.splitlines():
        if "trace_id=" in line:
            traces.append(line)
    
    # Parse trace details
    trace_details = []
    for trace_line in traces:
        detail = {}
        for match in re.finditer(r"(\w+)=([\w\[\]',\-\.{}:\" ]+?)(?=\s+\w+=|$)", trace_line):
            key, value = match.groups()
            detail[key] = value.strip()
        if detail:
            trace_details.append(detail)
    
    # Extract response IDs and call sequences
    response_matches = re.findall(
        r"openai_response_id=(resp_[a-f0-9]+)\s+.*?call_seq=(\d+)",
        text
    )
    
    # Extract session updates
    update_matches = re.findall(r"Updated session ([a-f0-9-]+), version (\d+)", text)
    
    return {
        "session_id": session_id,
        "traces": trace_details,
        "responses": response_matches,
        "updates": update_matches,
    }


def diagnose(result: dict) -> dict:
    """Diagnose common issues from parsed log."""
    issues = []
    recommendations = []
    
    session_id = result.get("session_id")
    traces = result.get("traces", [])
    
    if not session_id:
        issues.append("❌ No session creation found")
        return {"issues": issues, "recommendations": []}
    
    # Check all traces for stage and allow_persist
    stages_seen = set()
    persist_flags = []
    tools_exposed = []
    
    for trace in traces:
        stage = trace.get("stage", "").strip()
        allow_persist = trace.get("allow_persist", "").strip()
        tools = trace.get("tools", "").strip()
        
        if stage:
            stages_seen.add(stage)
        if allow_persist:
            persist_flags.append(allow_persist)
        if tools:
            tools_exposed.append(tools)
    
    # Issue: stuck in review_session
    if "review_session" in stages_seen and "apply_edits" not in stages_seen:
        issues.append("❌ Session stuck in 'review_session' stage (read-only)")
        recommendations.append(
            "→ User needs to explicitly confirm action (say 'yes', 'import prefill', etc.)"
        )
        recommendations.append(
            "→ Check if FSM is resolving PREPARE → REVIEW → CONFIRM correctly"
        )
    
    # Issue: allow_persist always False
    if persist_flags and all(p == "False" for p in persist_flags):
        issues.append("❌ Persistence disabled (allow_persist=False) for all calls")
        recommendations.append(
            "→ Stage must reach 'apply_edits' or 'fix_validation' to enable persistence"
        )
    
    # Issue: no persistence tools exposed
    has_update_cv_field = any("update_cv_field" in t for t in tools_exposed)
    if tools_exposed and not has_update_cv_field:
        issues.append("❌ No persistence tools (update_cv_field) exposed to model")
        recommendations.append(
            "→ Verify stage mapping: only 'apply_edits'/'fix_validation' expose persistence tools"
        )
    
    # Summary
    summary = {
        "session_id": session_id,
        "stages_seen": list(stages_seen),
        "persist_enabled": "True" in persist_flags,
        "persistence_tools_exposed": has_update_cv_field,
        "model_calls": len(result.get("responses", [])),
        "session_updates": len(result.get("updates", [])),
    }
    
    return {
        "summary": summary,
        "issues": issues,
        "recommendations": recommendations,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze_func_log.py <log_file>")
        sys.exit(1)
    
    log_path = Path(sys.argv[1])
    
    print(f"Analyzing log: {log_path.name}")
    print("=" * 80)
    
    result = parse_func_log(log_path)
    
    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)
    
    diagnosis = diagnose(result)
    
    # Print summary
    print("\n📊 Summary:")
    for key, value in diagnosis["summary"].items():
        print(f"  {key}: {value}")
    
    # Print issues
    if diagnosis["issues"]:
        print("\n⚠️  Issues Found:")
        for issue in diagnosis["issues"]:
            print(f"  {issue}")
    else:
        print("\n✅ No issues detected")
    
    # Print recommendations
    if diagnosis["recommendations"]:
        print("\n💡 Recommendations:")
        for rec in diagnosis["recommendations"]:
            print(f"  {rec}")
    
    print("\n" + "=" * 80)
    
    # Detailed traces
    if result["traces"]:
        print("\n📝 Detailed Traces:")
        for i, trace in enumerate(result["traces"], 1):
            print(f"\n  Call #{i}:")
            for key, value in trace.items():
                print(f"    {key}: {value}")


if __name__ == "__main__":
    main()
