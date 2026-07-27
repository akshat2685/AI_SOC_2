"""Field-level data classification and PII masking module."""
from enum import Enum
from typing import Dict, Any


class DataClassification(Enum):
    """Enumeration of data sensitivity classification levels."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


FIELD_CLASSIFICATIONS: Dict[str, DataClassification] = {
    "api_key": DataClassification.RESTRICTED,
    "password": DataClassification.RESTRICTED,
    "secret": DataClassification.RESTRICTED,
    "token": DataClassification.RESTRICTED,
    "ssn": DataClassification.RESTRICTED,
    "credit_card": DataClassification.RESTRICTED,
    "user_email": DataClassification.CONFIDENTIAL,
    "ip_address": DataClassification.CONFIDENTIAL,
    "alert_title": DataClassification.INTERNAL,
    "source_system": DataClassification.INTERNAL,
    "severity": DataClassification.INTERNAL,
    "os_version": DataClassification.PUBLIC,
}


def get_field_classification(field_name: str) -> DataClassification:
    """Retrieve the data classification level for a field name."""
    return FIELD_CLASSIFICATIONS.get(field_name.lower(), DataClassification.INTERNAL)


def mask_field(value: str, classification: DataClassification) -> str:
    """Mask sensitive or restricted string values."""
    if not isinstance(value, str) or not value:
        return ""
    if classification == DataClassification.RESTRICTED:
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * (len(value) - 4) + value[-2:]
    elif classification == DataClassification.CONFIDENTIAL:
        if len(value) <= 2:
            return "*" * len(value)
        return value[:1] + "*" * (len(value) - 2) + value[-1:]
    return value


def should_encrypt(field_name: str) -> bool:
    """Determine if a field requires at-rest or in-transit encryption."""
    classification = get_field_classification(field_name)
    return classification in (DataClassification.RESTRICTED, DataClassification.CONFIDENTIAL)
