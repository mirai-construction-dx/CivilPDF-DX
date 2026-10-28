"""Audit records for direct AI Provider calls (ADR-0007).

Every call that actually leaves this service for the AI Provider is written to
the hash-chained audit log with the same metadata shape:

- ``provider``   — always ``"anthropic"`` (the only provider allowed by ADR-0007)
- ``model``      — model name sent with the request
- ``operation``  — classify / extract / summary / query_expansion / connection_test
- ``sent_chars`` — number of characters sent (system prompt + user content)
- ``result``     — ``"success"`` or ``"error"`` (with ``error_type`` = exception class)

The actor is the audit row's ``user_id`` and the target document, if any, its
``resource_id``. Never recorded: the prompt, document text, search words, the
AI response, exception messages or any key.

Calls refused before sending (environment gate, kill switch off, missing key)
send nothing and are therefore not recorded here; the request itself is still
visible in the per-request access log written by ``AuditMiddleware``.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from services.audit_chain_service import create_chained_audit_log

PROVIDER = "anthropic"


def sent_chars(system: Optional[str], messages: Iterable[dict]) -> int:
    """Characters sent to the provider: system prompt plus message contents."""
    total = len(system or "")
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            total += len(content)
        else:  # list of content blocks
            for block in content or []:
                if isinstance(block, dict):
                    total += len(str(block.get("text", "")))
    return total


def provider_call_detail(
    *,
    operation: str,
    model: str,
    chars: int,
    result: str,
    error: Optional[BaseException] = None,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """JSON for the audit ``detail`` column. Metadata only, never content."""
    detail: dict[str, Any] = dict(extra or {})
    detail.update(
        {
            "provider": PROVIDER,
            "model": model,
            "operation": operation,
            "sent_chars": int(chars),
            "result": result,
        }
    )
    if error is not None:
        detail["error_type"] = error.__class__.__name__
    return json.dumps(detail, ensure_ascii=False)


def record_provider_call(
    db: Session,
    *,
    user_id: Optional[str],
    action: str,
    operation: str,
    model: str,
    chars: int,
    result: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    error: Optional[BaseException] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    create_chained_audit_log(
        db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=provider_call_detail(
            operation=operation,
            model=model,
            chars=chars,
            result=result,
            error=error,
            extra=extra,
        ),
        ip_address=None,
    )
