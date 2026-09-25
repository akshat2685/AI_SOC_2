"""Traffic Light Protocol (TLP) support for threat-intel objects.

Cyware-style handling: every indicator and feed carries a TLP marking that
controls how widely it may be shared. TLP 2.0 labels are used
(CLEAR replaces the old WHITE).
"""

from enum import Enum
from typing import Optional


class TLPLevel(str, Enum):
    CLEAR = "CLEAR"   # may be shared freely
    GREEN = "GREEN"   # share within the community
    AMBER = "AMBER"   # share within the organization (and clients on need-to-know)
    RED = "RED"       # do not share; named recipients only


# Accept common variants seen in the wild (MISP, TAXII, STIX).
_TLP_ALIASES = {
    "WHITE": TLPLevel.CLEAR,
    "TLP:WHITE": TLPLevel.CLEAR,
    "TLP:CLEAR": TLPLevel.CLEAR,
    "CLEAR": TLPLevel.CLEAR,
    "TLP:GREEN": TLPLevel.GREEN,
    "GREEN": TLPLevel.GREEN,
    "TLP:AMBER": TLPLevel.AMBER,
    "AMBER": TLPLevel.AMBER,
    "TLP:AMBER+STRICT": TLPLevel.AMBER,
    "TLP:RED": TLPLevel.RED,
    "RED": TLPLevel.RED,
}


def normalize_tlp(value: Optional[str]) -> str:
    """Normalize any TLP-ish string to a canonical TLPLevel value.

    Unknown / missing values default to CLEAR (least restrictive) so
    ingestion never crashes on a bad marking; callers that need strict
    handling should validate upstream.
    """
    if not value:
        return TLPLevel.CLEAR.value
    return _TLP_ALIASES.get(str(value).strip().upper(), TLPLevel.CLEAR.value)


def tlp_allows_distribution(tlp: Optional[str], target: str = "internal") -> bool:
    """Rough sharing check: can this marking be distributed to `target`?

    target is one of: "public", "community", "internal".
    """
    level = normalize_tlp(tlp)
    if target == "public":
        return level == TLPLevel.CLEAR.value
    if target == "community":
        return level in (TLPLevel.CLEAR.value, TLPLevel.GREEN.value)
    return True  # internal use is always allowed
