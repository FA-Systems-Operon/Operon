"""Typed conflict proposals and deterministic onboarding completeness rules (#43)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MandatoryField = Literal[
    "business_number",
    "website",
    "domain_platform",
    "meta_business_manager",
    "facebook_page",
    "instagram",
    "phone_number",
    "email",
    "business_address",
]
MANDATORY_FIELDS: tuple[MandatoryField, ...] = (
    "business_number",
    "website",
    "domain_platform",
    "meta_business_manager",
    "facebook_page",
    "instagram",
    "phone_number",
    "email",
    "business_address",
)
SCALAR_FIELDS = ("name", *MANDATORY_FIELDS)
_ITEM_PATH = r"(needs|goals)/(0|[1-9][0-9]*)"
REFERENCE_FIELD_PATTERN = r"^(" + "|".join(SCALAR_FIELDS) + "|" + _ITEM_PATH + r")$"
FIELD_PATTERN = r"^(" + "|".join(SCALAR_FIELDS) + r"|needs|goals|" + _ITEM_PATH + r")$"
NonBlank = Annotated[str, StringConstraints(pattern=r"\S")]


class OnboardingFields(BaseModel):
    """Nullable source-backed text; format validation is not a business requirement."""

    model_config = ConfigDict(extra="forbid", strict=True)
    business_number: NonBlank | None = None
    website: NonBlank | None = None
    domain_platform: NonBlank | None = None
    meta_business_manager: NonBlank | None = None
    facebook_page: NonBlank | None = None
    instagram: NonBlank | None = None
    phone_number: NonBlank | None = None
    email: NonBlank | None = None
    business_address: NonBlank | None = None


class ConflictAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: NonBlank
    document_id: NonBlank
    quote: NonBlank


class ProfileConflict(BaseModel):
    """A potential contradiction, never an automatic resolution."""

    model_config = ConfigDict(extra="forbid", strict=True)
    field: str = Field(pattern=FIELD_PATTERN)
    explanation: NonBlank
    alternatives: list[ConflictAlternative] = Field(min_length=2, max_length=2)


class ProfileAssessment(BaseModel):
    """Recomputed by the server; absent on historical, unassessed drafts."""

    model_config = ConfigDict(extra="forbid", strict=True)
    rules_version: Literal[1] = 1
    missing_fields: list[MandatoryField]


def assess_missing(data: dict, conflicts: list[ProfileConflict]) -> ProfileAssessment:
    conflict_fields = {conflict.field for conflict in conflicts}
    return ProfileAssessment(
        missing_fields=[
            field
            for field in MANDATORY_FIELDS
            if data.get(field) is None and field not in conflict_fields
        ]
    )
