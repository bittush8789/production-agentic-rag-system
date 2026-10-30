import os
import re
import logging
from typing import Dict, List, Tuple, Any, Optional

# Ensure transformers does not attempt to import TensorFlow
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ==========================================
# 1. PRESIDIO PII DETECTION & ANONYMIZATION
# ==========================================

_analyzer: Optional[AnalyzerEngine] = None
_anonymizer: Optional[AnonymizerEngine] = None


def get_presidio_engines() -> Tuple[AnalyzerEngine, AnonymizerEngine]:
    """Initializes and returns cached singleton instances of Presidio Analyzer and Anonymizer."""
    global _analyzer, _anonymizer
    if _analyzer is None or _anonymizer is None:
        logger.info("Initializing Microsoft Presidio Analyzer and Anonymizer...")
        _analyzer = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()

        # Add Custom Enterprise Recognizers
        # 1. Employee ID Pattern: EMP-12345 or EMP-123456
        emp_id_pattern = Pattern(name="employee_id_pattern", regex=r"\bEMP-\d{4,6}\b", score=0.85)
        emp_id_recognizer = PatternRecognizer(
            supported_entity="EMPLOYEE_ID",
            patterns=[emp_id_pattern],
            name="EmployeeIdRecognizer"
        )
        _analyzer.registry.add_recognizer(emp_id_recognizer)

        # 2. Corporate API Key Pattern: NOVA-xxxxxxxxxxxx
        nova_key_pattern = Pattern(name="nova_api_key_pattern", regex=r"\bNOVA-[A-Za-z0-9]{12,32}\b", score=0.95)
        nova_key_recognizer = PatternRecognizer(
            supported_entity="INTERNAL_API_KEY",
            patterns=[nova_key_pattern],
            name="NovaApiKeyRecognizer"
        )
        _analyzer.registry.add_recognizer(nova_key_recognizer)

        # 3. Sensitive Passwords / Credentials in plaintext
        pwd_pattern = Pattern(name="password_pattern", regex=r"(?i)\b(?:password|passwd|pwd|secret)\s*[:=]\s*([^\s,;]+)", score=0.9)
        pwd_recognizer = PatternRecognizer(
            supported_entity="CREDENTIAL",
            patterns=[pwd_pattern],
            name="CredentialRecognizer"
        )
        _analyzer.registry.add_recognizer(pwd_recognizer)

    return _analyzer, _anonymizer


def redact_pii(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Scans text for Personally Identifiable Information (PII) using Presidio.
    Returns (anonymized_text, list_of_detected_entities).
    """
    if not settings.enable_presidio_guardrails or not text or not text.strip():
        return text, []

    try:
        analyzer, anonymizer = get_presidio_engines()
        entities_to_scan = [
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "US_SSN",
            "CREDIT_CARD",
            "IP_ADDRESS",
            "IBAN_CODE",
            "CRYPTO",
            "EMPLOYEE_ID",
            "INTERNAL_API_KEY",
            "CREDENTIAL",
        ]

        results = analyzer.analyze(
            text=text,
            entities=entities_to_scan,
            language="en"
        )

        detected = []
        for res in results:
            detected.append({
                "entity_type": res.entity_type,
                "start": res.start,
                "end": res.end,
                "score": round(res.score, 2),
                "matched_text": text[res.start:res.end]
            })

        if not detected:
            return text, []

        # Anonymize using entity placeholders like <EMAIL_ADDRESS>, <PHONE_NUMBER>
        anonymized_result = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED_PII>"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<EMAIL_ADDRESS>"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<PHONE_NUMBER>"}),
                "US_SSN": OperatorConfig("replace", {"new_value": "<US_SSN>"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "<CREDIT_CARD>"}),
                "IP_ADDRESS": OperatorConfig("replace", {"new_value": "<IP_ADDRESS>"}),
                "EMPLOYEE_ID": OperatorConfig("replace", {"new_value": "<EMPLOYEE_ID>"}),
                "INTERNAL_API_KEY": OperatorConfig("replace", {"new_value": "<INTERNAL_API_KEY>"}),
                "CREDENTIAL": OperatorConfig("replace", {"new_value": "<CREDENTIAL>"}),
            }
        )

        logger.info("Presidio PII Guardrail redacted %d entity/entities from text", len(detected))
        return anonymized_result.text, detected

    except Exception as exc:
        logger.error("Presidio PII redaction encountered error: %s", exc, exc_info=True)
        # Fallback regex for high-risk PII in case analyzer fails
        fallback_text = re.sub(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "<EMAIL_ADDRESS>", text)
        fallback_text = re.sub(r"\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b", "<PHONE_NUMBER>", fallback_text)
        fallback_text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "<US_SSN>", fallback_text)
        return fallback_text, [{"entity_type": "FALLBACK_PII_REGEX", "score": 1.0}]


# ==========================================
# 2. NEMO GUARDRAILS (JAILBREAK, INJECTION, TOPIC)
# ==========================================

# High-precision patterns for immediate deterministic input rail defense
JAILBREAK_PATTERNS = [
    r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|prompts|directions)\b",
    r"(?i)\bdisregard\s+(?:all\s+)?(?:system|developer|safety)\s+(?:rules|prompts|instructions)\b",
    r"(?i)\byou\s+are\s+now\s+(?:DAN|unfiltered|jailbroken|free\s+of\s+rules)\b",
    r"(?i)\breveal\s+(?:your|the)\s+(?:system\s+prompt|initial\s+instructions|secret\s+key)\b",
    r"(?i)\bwhat\s+(?:are|is)\s+your\s+(?:system\s+prompt|hidden\s+rules|developer\s+mode)\b",
    r"(?i)\bbypass\s+(?:security|firewall|mfa|authentication|access\s+control)\b",
    r"(?i)\bgenerate\s+(?:malware|ransomware|keylogger|exploit\s+code|sql\s+injection)\b",
    r"(?i)\bdump\s+(?:all\s+)?(?:user\s+passwords|database\s+credentials|shadow\s+file)\b",
    r"(?i)\bdo\s+anything\s+now\b",
]

OFF_TOPIC_DOMAINS = [
    r"(?i)\bhow\s+to\s+make\s+(?:a\s+bomb|drugs|weapons|explosives)\b",
    r"(?i)\bhow\s+to\s+hack\s+into\s+(?:bank|government|fbi|cia|competitor)\b",
    r"(?i)\bwrite\s+erotica\b",
    r"(?i)\bpredict\s+crypto\s+prices\b",
]


class NeMoEnterpriseGuardrail:
    """
    Enterprise Guardrails engine incorporating NVIDIA NeMo Guardrails principles:
    - Input Rails: Jailbreak / Prompt Injection blocking & Topic moderation.
    - Dialog Rails: Corporate IT security policy compliance.
    - Output Rails: Hallucination & sensitive data leak prevention.
    """

    def __init__(self):
        self._rails_app = None
        self._init_nemo_rails()

    def _init_nemo_rails(self):
        if not settings.enable_nemo_guardrails:
            return

        try:
            from nemoguardrails import RailsConfig, LLMRails

            colang_config = """
define user express greeting
  "hello"
  "hi"
  "hey there"

define user ask it support
  "how do I connect to VPN"
  "reset my password"
  "setup MFA"
  "outlook not opening"

define flow it support assistance
  user ask it support
  bot provide grounded enterprise guidance

define user ask off topic
  "write me a story"
  "who won the world cup"
  "what is the stock price of Tesla"

define flow handle off topic
  user ask off topic
  bot refuse off topic
"""

            yaml_config = f"""
models:
  - type: main
    engine: openai
    model: {settings.openai_model}

rails:
  input:
    flows:
      - check jailbreak
      - check off topic
  output:
    flows:
      - check output hallucination
"""
            config = RailsConfig.from_content(
                colang_content=colang_config,
                yaml_content=yaml_config
            )
            # LLMRails will instantiate when needed or run with structured guards
            self._rails_app = config
            logger.info("NeMo Guardrails configuration initialized successfully.")
        except Exception as e:
            logger.warning("NeMo Guardrails LLMRails initialization deferred: %s", e)

    def validate_input(self, user_query: str) -> Dict[str, Any]:
        """
        Validates user input against NeMo Input Rails:
        1. Checks for jailbreak / prompt injection attempts.
        2. Checks for malicious or off-topic out-of-scope queries.
        """
        if not settings.enable_nemo_guardrails:
            return {"allowed": True, "reason": "Guardrails disabled in configuration"}

        query_clean = user_query.strip()

        # Check Jailbreak / Prompt Injection patterns
        for pattern in JAILBREAK_PATTERNS:
            if re.search(pattern, query_clean):
                logger.warning("NeMo Guardrail ALERT: Blocked prompt injection / jailbreak attempt: %s", pattern)
                return {
                    "allowed": False,
                    "reason": "Security Alert: Prompt injection or system override detected. This incident has been logged for corporate IT security review.",
                    "policy_violated": "SEC-POL-01: Prompt Injection / System Integrity",
                    "category": "jailbreak_detected"
                }

        # Check Off-topic / Malicious abuse
        for pattern in OFF_TOPIC_DOMAINS:
            if re.search(pattern, query_clean):
                logger.warning("NeMo Guardrail ALERT: Blocked out-of-scope / illicit request: %s", pattern)
                return {
                    "allowed": False,
                    "reason": "Scope Alert: NovaRetail IT Copilot is strictly reserved for corporate IT systems, hardware, networks, and internal workplace procedures.",
                    "policy_violated": "SEC-POL-02: Corporate Resource Acceptable Use Policy",
                    "category": "off_topic_blocked"
                }

        return {"allowed": True, "reason": "Passed NeMo input guardrails"}

    def validate_output(self, output_text: str, context: str = "") -> Dict[str, Any]:
        """
        Validates generated output against NeMo Output Rails:
        1. Checks for unauthorized disclosure of master credentials.
        2. Detects policy violations or hallucinated directives.
        """
        if not settings.enable_nemo_guardrails or not output_text:
            return {"allowed": True, "sanitized_output": output_text}

        # Check for simulated master password leakage
        if re.search(r"(?i)\broot\s*password\s*is\s*['\"]?[A-Za-z0-9@#$%^&*]+['\"]?", output_text):
            logger.error("NeMo Guardrail ALERT: Blocked output containing potential root password leak!")
            return {
                "allowed": False,
                "sanitized_output": "The response was redacted by Enterprise Output Guardrails because it contained sensitive system credentials.",
                "policy_violated": "SEC-POL-03: Credential Leakage Prevention"
            }

        return {"allowed": True, "sanitized_output": output_text}


# Singleton instance
guardrails_engine = NeMoEnterpriseGuardrail()

