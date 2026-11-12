"""Conservative validation of a provider body before isolated normalisation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_ERROR_MESSAGE = re.compile(r"\b(error|fail|denied|invalid|unauthori[sz]ed)\b|오류|실패|권한", re.I)


@dataclass(frozen=True)
class ResponseAssessment:
    state: str  # confirmed_success | schema_valid_unverified_code | rejected
    code: str | None
    record_count: int
    identity_record_count: int
    message_has_error: bool
    reason: str


def assess_list_response(
    payload: Any,
    records: Iterable[Mapping[str, Any]],
    *,
    id_field: str,
    title_field: str,
    confirmed_success_codes: frozenset[str],
) -> ResponseAssessment:
    """Classify body evidence without converting an undocumented code to success."""
    body = payload if isinstance(payload, dict) else {}
    code_value = body.get("resultCode")
    code = str(code_value).strip() if code_value is not None and str(code_value).strip() else None
    message = str(body.get("resultMsg") or "")
    items = [record for record in records if isinstance(record, Mapping)]
    identities = sum(bool(str(record.get(id_field) or "").strip()) and bool(str(record.get(title_field) or "").strip()) for record in items)
    message_has_error = bool(_ERROR_MESSAGE.search(message))
    if code is None:
        return ResponseAssessment("rejected", code, len(items), identities, message_has_error, "result_code_missing")
    if message_has_error:
        return ResponseAssessment("rejected", code, len(items), identities, True, "provider_error_message")
    if not items:
        return ResponseAssessment("rejected", code, 0, 0, False, "list_data_missing")
    if not identities:
        return ResponseAssessment("rejected", code, len(items), 0, False, "required_identity_fields_missing")
    if code in confirmed_success_codes:
        return ResponseAssessment("confirmed_success", code, len(items), identities, False, "documented_code_and_schema")
    return ResponseAssessment("schema_valid_unverified_code", code, len(items), identities, False, "schema_valid_code_not_documented")
