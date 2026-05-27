"""
Output Guardrail for Pharma Data Integrity Inspector
Uses Guardrails AI with custom validators when available, falls back to regex.
"""

import re
from typing import Dict, Any, List, Optional

try:
    from guardrails import Guard
    from guardrails.classes import ValidationResult
    from guardrails.validator_base import Validator
    HAS_GUARDRAILS = True
except ImportError:
    HAS_GUARDRAILS = False
    Validator = object
    ValidationResult = None


_PII_PATTERNS = [
    (re.compile(r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b'), '[SSN-REDACTED]'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL-REDACTED]'),
    (re.compile(r'\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), '[PHONE-REDACTED]'),
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '[IP-REDACTED]'),
    (re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b'), '[NAME-REDACTED]'),
]

_PHARMA_PATTERNS = [
    (re.compile(r'\b[A-Z]{2,3}[-]?\d{5,8}\b'), '[BATCH-REDACTED]'),
    (re.compile(r'\bLot\s*(?:#|Number|No\.?)?\s*[A-Z0-9-]{4,}\b', re.IGNORECASE), '[LOT-REDACTED]'),
    (re.compile(r'\bpatient\s+(?:name|id|record|info|data|identifier)\b', re.IGNORECASE), '[PATIENT-REF-REDACTED]'),
    (re.compile(r'\bformulation\s+(?:recipe|composition|mixture|ratio)\b', re.IGNORECASE), '[FORMULATION-REDACTED]'),
    (re.compile(r'\bproprietary\s+(?:process|method|formula|blend)\b', re.IGNORECASE), '[PROPRIETARY-REDACTED]'),
]

_CREDENTIAL_PATTERNS = [
    (re.compile(r'\bPASS(?:WORD)?\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
    (re.compile(r'\bAPI[_-]?KEY\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
    (re.compile(r'\bSECRET\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
    (re.compile(r'\bTOKEN\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
]

_DANGEROUS_PATTERNS = [
    re.compile(r'\bbypass\s+(?:the\s+)?(?:audit\s+trail|quality\s+check|security|authentication)\b', re.IGNORECASE),
    re.compile(r'\bignore\s+(?:the\s+)?(?:FDA|regulation|compliance|validation|SOP)\b', re.IGNORECASE),
    re.compile(r'\bdelete\s+(?:the\s+)?(?:audit|log|record|trail)\b', re.IGNORECASE),
    re.compile(r'\bdisable\s+(?:the\s+)?(?:alarm|alert|monitoring|safety)\b', re.IGNORECASE),
    re.compile(r'\bskip\s+(?:the\s+)?(?:calibration|validation|testing|inspection)\b', re.IGNORECASE),
    re.compile(r'\baccess\s+(?:restricted|unauthorized|confidential)\b', re.IGNORECASE),
]

_ALL_REDACTION_PATTERNS = _PII_PATTERNS + _PHARMA_PATTERNS + _CREDENTIAL_PATTERNS


if HAS_GUARDRAILS:
    class PIIValidator(Validator):
        risk_type = "pii"
        pod_manager_type = ""

        def validate(self, value: Any, metadata: Dict = {}) -> ValidationResult:
            if not value or not isinstance(value, str):
                return ValidationResult(value=value, validation_passed=True)
            result = value
            for pattern, replacement in _PII_PATTERNS:
                result = pattern.sub(replacement, result)
            return ValidationResult(value=result, validation_passed=(result == value))

    class PharmaSensitiveValidator(Validator):
        risk_type = "pharma_sensitive"
        pod_manager_type = ""

        def validate(self, value: Any, metadata: Dict = {}) -> ValidationResult:
            if not value or not isinstance(value, str):
                return ValidationResult(value=value, validation_passed=True)
            result = value
            for pattern, replacement in _PHARMA_PATTERNS:
                result = pattern.sub(replacement, result)
            return ValidationResult(value=result, validation_passed=(result == value))

    class CredentialValidator(Validator):
        risk_type = "credentials"
        pod_manager_type = ""

        def validate(self, value: Any, metadata: Dict = {}) -> ValidationResult:
            if not value or not isinstance(value, str):
                return ValidationResult(value=value, validation_passed=True)
            result = value
            for pattern, replacement in _CREDENTIAL_PATTERNS:
                result = pattern.sub(replacement, result)
            return ValidationResult(value=result, validation_passed=(result == value))

    class DangerousRecommendationValidator(Validator):
        risk_type = "dangerous_recommendation"
        pod_manager_type = ""

        def validate(self, value: Any, metadata: Dict = {}) -> ValidationResult:
            if not value or not isinstance(value, str):
                return ValidationResult(value=value, validation_passed=True)
            for pattern in _DANGEROUS_PATTERNS:
                if pattern.search(value):
                    return ValidationResult(
                        value="[GUARDRAIL: This recommendation was blocked as it suggests an unsafe action. Please consult your SOP and QA team.]",
                        validation_passed=False
                    )
            return ValidationResult(value=value, validation_passed=True)


class OutputGuardrail:
    """Validates and sanitizes agent outputs using Guardrails AI when available, regex fallback otherwise."""

    def __init__(self):
        if HAS_GUARDRAILS:
            self.text_guard = Guard()\
                .use(PIIValidator, on_fail="fix")\
                .use(PharmaSensitiveValidator, on_fail="fix")\
                .use(CredentialValidator, on_fail="fix")
            self.action_guard = Guard()\
                .use(DangerousRecommendationValidator, on_fail="fix")
        else:
            self.text_guard = None
            self.action_guard = None

    def sanitize_text(self, text: str) -> str:
        if not text or not isinstance(text, str):
            return text
        if self.text_guard is not None:
            try:
                result = self.text_guard.validate(text)
                return result.validated_output
            except Exception:
                pass
        for pattern, replacement in _ALL_REDACTION_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def check_recommendation(self, action: str) -> tuple:
        if not action or not isinstance(action, str):
            return True, ""
        if self.action_guard is not None:
            try:
                result = self.action_guard.validate(action)
                if result.validation_passed:
                    return True, ""
                return False, "Blocked recommendation: dangerous action detected"
            except Exception:
                pass
        for pattern in _DANGEROUS_PATTERNS:
            if pattern.search(action):
                return False, f"Blocked recommendation: contains unsafe suggestion matching '{pattern.pattern}'"
        return True, ""

    def validate_hypothesis(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(hypothesis)
        guardrail_log = []

        text_fields = ["root_cause", "recommended_action", "pharma_impact"]
        for field in text_fields:
            original = result.get(field, "")
            if original:
                sanitized = self.sanitize_text(original)
                if sanitized != original:
                    guardrail_log.append(f"REDACTED: {field} - sensitive information removed")
                    result[field] = sanitized

        alternative_causes = result.get("alternative_causes", [])
        if isinstance(alternative_causes, list):
            sanitized_causes = []
            for cause in alternative_causes:
                s = self.sanitize_text(str(cause))
                if s != str(cause):
                    guardrail_log.append("REDACTED: alternative_cause - sensitive information removed")
                sanitized_causes.append(s)
            result["alternative_causes"] = sanitized_causes

        action = result.get("recommended_action", "")
        is_safe, reason = self.check_recommendation(action)
        if not is_safe:
            guardrail_log.append(f"BLOCKED: {reason}")
            result["recommended_action"] = "[GUARDRAIL: This recommendation was blocked as it suggests an unsafe action. Please consult your SOP and QA team.]"
            result["_guardrail_blocked"] = True

        confidence = result.get("confidence", 0.5)
        if isinstance(confidence, (int, float)):
            result["confidence"] = min(1.0, max(0.0, float(confidence)))
        else:
            result["confidence"] = 0.5
            guardrail_log.append("FIXED: confidence bounded to [0, 1]")

        if guardrail_log:
            result["_guardrail_log"] = guardrail_log

        return result

    def validate_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(report_data)
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 10:
                result[key] = self.sanitize_text(value)
            elif isinstance(value, dict):
                result[key] = self.validate_report(value)
            elif isinstance(value, list):
                result[key] = [
                    self.sanitize_text(v) if isinstance(v, str) and len(v) > 10 else v
                    for v in value
                ]
        return result


guardrail = OutputGuardrail()