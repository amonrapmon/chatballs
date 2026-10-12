"""Persistent codes; presentation belongs to the request-language catalog."""

from django.db import models


class WorkStatus(models.TextChoices):
    READY = "READY"
    BUSY = "BUSY"
    BREAK = "BREAK"
    UNAVAILABLE = "UNAVAILABLE"
