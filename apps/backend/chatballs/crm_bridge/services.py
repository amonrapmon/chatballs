"""Atomic CRM settings mutations. All queries are scoped to an Organization.

Serializing on the organization row prevents competing primary/binding changes.
"""

from __future__ import annotations

import re

from django.db import transaction

from chatballs.crm_bridge.models import (
    CRMCompany,
    CRMConnectionBinding,
    CRMOrganizationConfig,
    CRMProvider,
)
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind


class CRMConfigurationError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def _lock_organization(organization_id: int) -> None:
    Organization.objects.select_for_update().get(pk=organization_id)


def _provider(value: object) -> str:
    if not isinstance(value, str) or value not in CRMProvider.values:
        raise CRMConfigurationError("invalid_provider")
    return value


def _company_data(name: object, external_company_id: object) -> tuple[str, str]:
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 160):
        raise CRMConfigurationError("invalid_company_name")
    if (
        not isinstance(external_company_id, str)
        or len(external_company_id) > 40
        or re.fullmatch(r"[0-9]+", external_company_id) is None
    ):
        raise CRMConfigurationError("invalid_external_company_id")
    return name.strip(), external_company_id


def _boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise CRMConfigurationError("invalid_" + field)
    return value


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise CRMConfigurationError("invalid_" + field)
    return value


def _get_config(organization_id: int) -> CRMOrganizationConfig:
    config, _ = CRMOrganizationConfig.objects.get_or_create(
        organization_id=organization_id
    )
    return config


def _assert_enabled(organization_id: int) -> None:
    if not CRMOrganizationConfig.objects.filter(
        organization_id=organization_id,
        provider__in=(CRMProvider.YCLIENTS, CRMProvider.DIKIDI),
    ).exists():
        raise CRMConfigurationError("crm_disabled", 409)


def _set_primary(*, organization_id: int, replacement_id: int | None = None) -> None:
    CRMCompany.objects.filter(
        organization_id=organization_id, is_primary=True
    ).exclude(pk=replacement_id).update(is_primary=False)


@transaction.atomic
def set_provider(*, organization_id: int, provider: object) -> tuple[CRMOrganizationConfig, bool]:
    selected = _provider(provider)
    _lock_organization(organization_id)
    config = _get_config(organization_id)
    if config.provider == selected:
        return config, False
    existing = CRMCompany.objects.filter(organization_id=organization_id).exists()
    if selected == CRMProvider.NONE:
        if config.provider != CRMProvider.NONE:
            config.last_active_provider = config.provider
    else:
        if existing and config.last_active_provider != selected:
            raise CRMConfigurationError("provider_has_existing_companies", 409)
        if existing and config.provider not in (CRMProvider.NONE, selected):
            raise CRMConfigurationError("provider_has_existing_companies", 409)
        config.last_active_provider = selected
    config.provider = selected
    config.full_clean()
    config.save(update_fields=["provider", "last_active_provider"])
    return config, True


@transaction.atomic
def create_company(
    *, organization_id: int, name: object, external_company_id: object,
    is_primary: object = False, is_active: object = True,
) -> CRMCompany:
    _lock_organization(organization_id)
    _assert_enabled(organization_id)
    clean_name, clean_id = _company_data(name, external_company_id)
    primary = _boolean(is_primary, "is_primary")
    active = _boolean(is_active, "is_active")
    if primary and not active:
        raise CRMConfigurationError("inactive_primary", 409)
    # First active company becomes primary; later changes are explicit.
    if active and not CRMCompany.objects.filter(
        organization_id=organization_id, is_primary=True
    ).exists():
        primary = True
    if primary:
        _set_primary(organization_id=organization_id)
    company = CRMCompany(
        organization_id=organization_id, name=clean_name,
        external_company_id=clean_id, is_primary=primary, is_active=active,
    )
    company.full_clean()
    company.save()
    return company


@transaction.atomic
def update_company(*, organization_id: int, company_id: int, changes: dict) -> tuple[CRMCompany, bool]:
    _lock_organization(organization_id)
    company = CRMCompany.objects.filter(
        organization_id=organization_id, pk=company_id
    ).first()
    if company is None:
        raise CRMConfigurationError("company_not_found", 404)
    allowed = {"name", "externalCompanyId", "isPrimary", "isActive"}
    if not changes or set(changes) - allowed:
        raise CRMConfigurationError("invalid_company_update")
    name = changes.get("name", company.name)
    external_id = changes.get("externalCompanyId", company.external_company_id)
    company.name, company.external_company_id = _company_data(name, external_id)
    primary = _boolean(changes.get("isPrimary", company.is_primary), "is_primary")
    active = _boolean(changes.get("isActive", company.is_active), "is_active")
    if primary and not active:
        raise CRMConfigurationError("inactive_primary", 409)
    if company.is_primary and not primary and CRMCompany.objects.filter(
        organization_id=organization_id, is_active=True
    ).exclude(pk=company.pk).exists():
        raise CRMConfigurationError("reassign_primary_first", 409)
    current = CRMCompany.objects.get(pk=company_id, organization_id=organization_id)
    changed = (
        (company.name != current.name) or
        (company.external_company_id != current.external_company_id) or
        (primary != current.is_primary) or (active != current.is_active)
    )
    if changed:
        if primary and not current.is_primary:
            _set_primary(organization_id=organization_id)
        company.is_primary = primary
        company.is_active = active
        company.full_clean()
        company.save()
    return company, changed


@transaction.atomic
def delete_company(*, organization_id: int, company_id: int) -> None:
    _lock_organization(organization_id)
    company = CRMCompany.objects.filter(
        organization_id=organization_id, pk=company_id
    ).first()
    if company is None:
        raise CRMConfigurationError("company_not_found", 404)
    if CRMConnectionBinding.objects.filter(
        organization_id=organization_id, crm_company=company
    ).exists():
        raise CRMConfigurationError("company_has_bindings", 409)
    if company.is_primary and CRMCompany.objects.filter(
        organization_id=organization_id, is_active=True
    ).exclude(pk=company.pk).exists():
        raise CRMConfigurationError("reassign_primary_first", 409)
    company.delete()


@transaction.atomic
def set_binding(
    *, organization_id: int, integration_id: int, company_id: object,
) -> tuple[CRMConnectionBinding, bool]:
    _lock_organization(organization_id)
    _assert_enabled(organization_id)
    target_id = _positive_int(company_id, "company_id")
    integration = Integration.objects.filter(
        pk=integration_id, organization_id=organization_id,
        kind=IntegrationKind.MESSENGER,
    ).first()
    if integration is None:
        raise CRMConfigurationError("integration_not_found", 404)
    company = CRMCompany.objects.filter(
        pk=target_id, organization_id=organization_id, is_active=True
    ).first()
    if company is None:
        raise CRMConfigurationError("company_not_found", 404)
    binding = CRMConnectionBinding.objects.filter(
        organization_id=organization_id, integration=integration
    ).first()
    if binding is not None:
        if binding.crm_company_id == company.id:
            return binding, False
        binding.crm_company = company
        binding.full_clean()
        binding.save(update_fields=["crm_company"])
        return binding, True
    binding = CRMConnectionBinding(
        organization_id=organization_id, integration=integration, crm_company=company
    )
    binding.full_clean()
    binding.save()
    return binding, True


@transaction.atomic
def delete_binding(*, organization_id: int, integration_id: int) -> bool:
    _lock_organization(organization_id)
    deleted, _ = CRMConnectionBinding.objects.filter(
        organization_id=organization_id, integration_id=integration_id
    ).delete()
    return bool(deleted)
