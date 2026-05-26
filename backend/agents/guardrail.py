"""
Output Guardrail for Pharma Data Integrity Inspector
Sanitizes LLM output to prevent sensitive information leakage.
"""

import re
from typing import Dict, Any, List


class OutputGuardrail:
    """Validates and sanitizes agent outputs before they reach the user or database"""

    REDACTION_PATTERNS = [
        (re.compile(r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b'), '[SSN-REDACTED]'),
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL-REDACTED]'),
        (re.compile(r'\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'), '[PHONE-REDACTED]'),
        (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '[IP-REDACTED]'),
        (re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b'), '[NAME-REDACTED]'),
        (re.compile(r'\bPASS(?:WORD)?\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
        (re.compile(r'\bAPI[_-]?KEY\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
        (re.compile(r'\bSECRET\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
        (re.compile(r'\bTOKEN\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL-REDACTED]'),
    ]

    PHARMA_SENSITIVE_PATTERNS = [
        (re.compile(r'\b[A-Z]{2,3}[-]?\d{5,8}\b'), '[BATCH-REDACTED]'),
        (re.compile(r'\bLot\s*(?:#|Number|No\.?)?\s*[A-Z0-9-]{4,}\b', re.IGNORECASE), '[LOT-REDACTED]'),
        (re.compile(r'\bpatient\s+(?:name|id|record|info|data|identifier)\b', re.IGNORECASE), '[PATIENT-REF-REDACTED]'),
        (re.compile(r'\bformulation\s+(?:recipe|composition|mixture|ratio)\b', re.IGNORECASE), '[FORMULATION-REDACTED]'),
        (re.compile(r'\bproprietary\s+(?:process|method|formula|blend)\b', re.IGNORECASE), '[PROPRIETARY-REDACTED]'),
    ]

    BLOCKED_RECOMMENDATION_PATTERNS = [
        re.compile(r'\bbypass\s+(?:the\s+)?(?:audit\s+trail|quality\s+check|security|authentication)\b', re.IGNORECASE),
        re.compile(r'\bignore\s+(?:the\s+)?(?:FDA|regulation|compliance|validation|SOP)\b', re.IGNORECASE),
        re.compile(r'\bdelete\s+(?:the\s+)?(?:audit|log|record|trail)\b', re.IGNORECASE),
        re.compile(r'\bdisable\s+(?:the\s+)?(?:alarm|alert|monitoring|safety)\b', re.IGNORECASE),
        re.compile(r'\bskip\s+(?:the\s+)?(?:calibration|validation|testing|inspection)\b', re.IGNORECASE),
        re.compile(r'\baccess\s+(?:restricted|unauthorized|confidential)\b', re.IGNORECASE),
    ]

    def sanitize_text(self, text: str) -> str:
        """Remove PII and sensitive information from text"""
        if not text or not isinstance(text, str):
            return text
        sanitized = text
        for pattern, replacement in self.REDACTION_PATTERNS + self.PHARMA_SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    def check_recommendation(self, action: str) -> tuple:
        """Check if a recommended action contains dangerous suggestions.
        Returns (is_safe, reason) tuple."""
        if not action or not isinstance(action, str):
            return True, ""
        for pattern in self.BLOCKED_RECOMMENDATION_PATTERNS:
            if pattern.search(action):
                return False, f"Blocked recommendation: contains unsafe suggestion matching '{pattern.pattern}'"
        return True, ""

    def validate_hypothesis(self, hypothesis: Dict[str, Any]) -> Dict[str, Any]:
        """Full guardrail validation on a hypothesis output.
        Sanitizes text fields and blocks dangerous recommendations."""
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
        """Sanitize any free-text fields in report data"""
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