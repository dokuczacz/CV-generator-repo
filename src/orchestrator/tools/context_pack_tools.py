from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ContextPackToolDeps:
    cv_delta_mode: bool
    build_context_pack_v2: Callable[..., dict]
    build_context_pack_v2_delta: Callable[..., dict]


def tool_generate_context_pack_v2(
    *,
    session_id: str,
    phase: str,
    job_posting_text: str | None,
    max_pack_chars: int,
    session: dict,
    deps: ContextPackToolDeps,
) -> tuple[int, dict]:
    if phase not in ["preparation", "confirmation", "execution"]:
        return 400, {"error": "Invalid phase. Must be 'preparation', 'confirmation', or 'execution'"}

    cv_data = session.get("cv_data") or {}
    metadata = session.get("metadata") or {}
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        metadata["session_id"] = session_id

    if deps.cv_delta_mode and metadata.get("section_hashes_prev"):
        pack = deps.build_context_pack_v2_delta(
            phase=phase,
            cv_data=cv_data,
            session_metadata=metadata,
            job_posting_text=job_posting_text,
            max_pack_chars=max_pack_chars,
        )
    else:
        pack = deps.build_context_pack_v2(
            phase=phase,
            cv_data=cv_data,
            job_posting_text=job_posting_text,
            session_metadata=metadata,
            max_pack_chars=max_pack_chars,
        )
    return 200, pack
