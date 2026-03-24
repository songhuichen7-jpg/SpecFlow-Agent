"""Template library package."""

from specflow.templates.library import TemplateAsset, TemplateLibrary, get_default_template_library
from specflow.templates.profiles import (
    DEFAULT_TARGET_STACK,
    DEFAULT_TEMPLATE_PROFILE,
    DEFAULT_TEMPLATE_SLUG,
    DEFAULT_TEMPLATE_VERSION,
    TemplateApiDefinition,
    TemplateEntityDefinition,
    TemplateEntityField,
    TemplatePageDefinition,
    TemplateProfileDefinition,
    ensure_template_profile_record,
    get_template_profile_definition,
)

__all__ = [
    "DEFAULT_TARGET_STACK",
    "DEFAULT_TEMPLATE_PROFILE",
    "DEFAULT_TEMPLATE_SLUG",
    "DEFAULT_TEMPLATE_VERSION",
    "TemplateApiDefinition",
    "TemplateAsset",
    "TemplateEntityDefinition",
    "TemplateEntityField",
    "TemplateLibrary",
    "TemplatePageDefinition",
    "TemplateProfileDefinition",
    "ensure_template_profile_record",
    "get_default_template_library",
    "get_template_profile_definition",
]
