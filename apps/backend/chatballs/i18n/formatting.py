"""Server counterpart of fmt: use the selected locale's number conventions."""

from django.utils import formats, translation


def fmt(value, *, language):
    with translation.override(language):
        return formats.number_format(value, use_l10n=True, force_grouping=True)
