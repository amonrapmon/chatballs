"""Conservative classification from server-verified evidence only.

The adapter is responsible for corroborating correlation IDs and employee
membership against the current integration/tenant. Untrusted payload flags
are NOT authentication evidence. In particular, an unknown VK author is
not a confirmed employee and cannot implicitly supersede an AI response.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OriginClass(StrEnum):
    SELF_ECHO = "self_echo"
    EXTERNAL_AUTHORIZED = "external_authorized"
    EXTERNAL_UNCLASSIFIED = "external_unclassified"


@dataclass(frozen=True, slots=True)
class VerifiedEvidence:
    source_authenticated: bool = False
    own_outbound_correlated: bool = False
    staff_membership_verified: bool = False


def classify_origin(evidence: VerifiedEvidence) -> OriginClass:
    """Do not infer a human from an unmatched outgoing provider event."""
    if not evidence.source_authenticated:
        return OriginClass.EXTERNAL_UNCLASSIFIED
    if evidence.own_outbound_correlated and evidence.staff_membership_verified:
        # Conflicting signals are not sufficient to attribute a human author.
        return OriginClass.EXTERNAL_UNCLASSIFIED
    if evidence.own_outbound_correlated:
        return OriginClass.SELF_ECHO
    if evidence.staff_membership_verified:
        return OriginClass.EXTERNAL_AUTHORIZED
    return OriginClass.EXTERNAL_UNCLASSIFIED
