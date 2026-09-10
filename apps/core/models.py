"""
apps/core/models.py
=====================
Abstract OOP base models used across all Sifo Drive apps.

Inheritance hierarchy:
──────────────────────────────────────────────────────────
  TimeStampedModel   — created_at / updated_at
  UUIDModel          — UUID4 primary key (no sequential int exposure)
  SoftDeleteModel    — is_deleted / deleted_at / deleted_by
                       + SoftDeleteManager (filters deleted by default)
  BaseModel          — UUIDModel + TimeStampedModel + SoftDeleteModel  ← use this
  OwnedModel         — BaseModel + owner FK
  OrderedModel       — BaseModel + sort_order
  PublishableModel   — BaseModel + is_published / published_at / published_by
  StatusModel        — BaseModel + generic status field + transition helpers
──────────────────────────────────────────────────────────

Rules:
  1. All domain models MUST inherit from BaseModel (or a subclass of it).
  2. Never use raw integer PKs in this project.
  3. All deletions MUST be soft deletions (call .delete(deleted_by=user)).
     Hard-delete is available as .hard_delete() and requires explicit intent.
  4. created_by / updated_by are NOT on BaseModel — add them per-model when
     needed (so BaseModel doesn't create a circular dep with accounts.User).
"""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# QuerySet
# ---------------------------------------------------------------------------

class SoftDeleteQuerySet(models.QuerySet):
    """
    QuerySet that is soft-delete-aware.
    The default manager automatically filters to alive() records;
    use all_objects or all_with_deleted() to bypass.
    """

    def alive(self) -> "SoftDeleteQuerySet":
        """Return only non-deleted records."""
        return self.filter(is_deleted=False)

    def deleted(self) -> "SoftDeleteQuerySet":
        """Return only soft-deleted records."""
        return self.filter(is_deleted=True)

    def delete(self, deleted_by=None) -> tuple[int, dict]:
        """
        Bulk soft-delete: sets is_deleted=True, deleted_at=now() on
        every record in this queryset. Returns (count, {}) like Django's delete().
        """
        now = timezone.now()
        updates = {"is_deleted": True, "deleted_at": now}
        if deleted_by is not None:
            updates["deleted_by"] = deleted_by
        count = self.update(**updates)
        return count, {}

    def hard_delete(self) -> tuple[int, dict]:
        """Permanently remove records. Bypasses soft-delete. Use with caution."""
        return super().delete()

    def restore(self) -> int:
        """Restore all soft-deleted records in this queryset."""
        return self.update(is_deleted=False, deleted_at=None, deleted_by=None)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    """
    Default manager: automatically filters out soft-deleted records.
    Use Model.all_objects to access the raw, unfiltered queryset.
    """

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).alive()

    def all_with_deleted(self) -> SoftDeleteQuerySet:
        """Return all records including soft-deleted."""
        return SoftDeleteQuerySet(self.model, using=self._db)

    def only_deleted(self) -> SoftDeleteQuerySet:
        """Return only soft-deleted records."""
        return SoftDeleteQuerySet(self.model, using=self._db).deleted()


# ---------------------------------------------------------------------------
# TimeStampedModel
# ---------------------------------------------------------------------------

class TimeStampedModel(models.Model):
    """
    Abstract base providing created_at and updated_at timestamps.
    Both are server-set via auto_now_add / auto_now — never client-supplied.
    """

    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
        db_index=True,
        help_text=_("Server-side timestamp of record creation."),
    )
    updated_at = models.DateTimeField(
        _("Updated At"),
        auto_now=True,
        db_index=True,
        help_text=_("Server-side timestamp of last modification."),
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# UUIDModel
# ---------------------------------------------------------------------------

class UUIDModel(models.Model):
    """
    Abstract base replacing the default integer PK with a UUID4.

    Benefits:
      - No sequential ID enumeration (security)
      - Safe to share across services without collision
      - Can be generated client-side before the record is saved (idempotency)
    """

    id = models.UUIDField(
        _("ID"),
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique UUID4 identifier. Generated automatically."),
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# SoftDeleteModel
# ---------------------------------------------------------------------------

class SoftDeleteModel(models.Model):
    """
    Abstract base providing logical (soft) deletion.

    Records are NEVER hard-deleted — they are flagged with is_deleted=True
    and a deletion timestamp. This preserves referential integrity and
    satisfies the 7-year data retention requirement.

    Manager behaviour:
      Model.objects          → alive records only  (default, production-safe)
      Model.all_objects      → all records including deleted  (raw Django manager)
      Model.objects.only_deleted() → soft-deleted records only

    Instance methods:
      instance.delete(deleted_by=user)  → soft delete
      instance.hard_delete()            → permanent removal (requires justification)
      instance.restore()                → un-delete
    """

    is_deleted = models.BooleanField(
        _("Is Deleted"),
        default=False,
        db_index=True,
    )
    deleted_at = models.DateTimeField(
        _("Deleted At"),
        null=True,
        blank=True,
    )
    deleted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_deletions",
        verbose_name=_("Deleted By"),
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()  # Unfiltered — use explicitly when needed

    class Meta:
        abstract = True

    def delete(self, deleted_by=None, using=None, keep_parents=False) -> None:
        """
        Soft-delete this record.

        Args:
            deleted_by: The User performing the deletion (for audit trail).
                        Stored as deleted_by FK.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by is not None:
            self.deleted_by = deleted_by
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def hard_delete(self, using=None, keep_parents=False):
        """
        Permanently remove this record from the database.
        Only use when legally required (e.g., GDPR/NCSA right-to-erasure PII purge).
        """
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self, restored_by=None) -> None:
        """Restore a soft-deleted record back to active state."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    @property
    def is_alive(self) -> bool:
        return not self.is_deleted


# ---------------------------------------------------------------------------
# BaseModel  (the recommended default for all domain models)
# ---------------------------------------------------------------------------

class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """
    Primary abstract base model for all Sifo Drive domain entities.

    Provides:
      - UUID4 primary key        (UUIDModel)
      - created_at / updated_at  (TimeStampedModel)
      - Soft delete support      (SoftDeleteModel)

    Usage:
        class MyModel(BaseModel):
            name = models.CharField(max_length=100)

            class Meta(BaseModel.Meta):
                verbose_name = "My Model"
    """

    class Meta(TimeStampedModel.Meta):
        abstract = True
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Specialised base models
# ---------------------------------------------------------------------------

class OwnedModel(BaseModel):
    """
    Abstract base for records that belong to a specific user.

    Adds a required owner FK and enforces that the related_name
    is unique per app+class so reverse lookups don't clash.
    """

    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_owned",
        verbose_name=_("Owner"),
        db_index=True,
    )

    class Meta(BaseModel.Meta):
        abstract = True


class OrderedModel(BaseModel):
    """
    Abstract base for records that need explicit ordering
    within a parent container (e.g. Lessons within a Module,
    Options within a QuizQuestion).
    """

    sort_order = models.PositiveIntegerField(
        _("Sort Order"),
        default=0,
        db_index=True,
        help_text=_(
            "Controls the display ordering of this record within its parent. "
            "Lower values appear first."
        ),
    )

    class Meta(BaseModel.Meta):
        abstract = True
        ordering = ["sort_order", "-created_at"]

    def move_to(self, new_order: int) -> None:
        """Update sort_order without triggering full model save."""
        self.sort_order = new_order
        self.save(update_fields=["sort_order", "updated_at"])


class PublishableModel(BaseModel):
    """
    Abstract base for content entities that have a publish/draft lifecycle
    (Courses, Modules, Lessons, LiveClasses, etc.).

    States:
      is_published=False  → draft, not visible to learners
      is_published=True   → live, visible to learners

    The published_at timestamp and published_by FK are set automatically
    when publish() is called.
    """

    is_published = models.BooleanField(
        _("Published"),
        default=False,
        db_index=True,
    )
    published_at = models.DateTimeField(
        _("Published At"),
        null=True,
        blank=True,
    )
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_published",
        verbose_name=_("Published By"),
    )

    class Meta(BaseModel.Meta):
        abstract = True

    def publish(self, published_by=None) -> None:
        """Make this content live and visible to learners."""
        if self.is_published:
            return  # Idempotent
        self.is_published = True
        self.published_at = timezone.now()
        if published_by:
            self.published_by = published_by
        self.save(update_fields=["is_published", "published_at", "published_by", "updated_at"])

    def unpublish(self) -> None:
        """Pull content back to draft."""
        if not self.is_published:
            return  # Idempotent
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])


class StatusModel(BaseModel):
    """
    Abstract base for models that progress through a named status lifecycle
    (e.g. BookingOrder states, ExamSession states, Transaction states).

    Subclasses must define:
        STATUS_CHOICES: list[tuple[str, str]]
        status = models.CharField(choices=STATUS_CHOICES, ...)

    Provides:
        transition_to(new_status)  — validates + records the change
        status_changed_at          — timestamp of last status change

    Example:
        class BookingOrder(StatusModel):
            STATUS_CHOICES = [('QUEUED', 'Queued'), ('CONFIRMED', 'Confirmed')]
            status = models.CharField(choices=STATUS_CHOICES, default='QUEUED', max_length=20)
    """

    status_changed_at = models.DateTimeField(
        _("Status Changed At"),
        null=True,
        blank=True,
        help_text=_("Timestamp of the last status transition."),
    )

    class Meta(BaseModel.Meta):
        abstract = True

    def transition_to(self, new_status: str, save: bool = True) -> None:
        """
        Perform a status transition.

        Args:
            new_status: The target status value. Must be in the model's STATUS_CHOICES.
            save: If True (default), saves the record immediately.

        Raises:
            ValueError if new_status is not a valid choice.
        """
        valid = {choice[0] for choice in self.__class__._meta.get_field("status").choices}
        if new_status not in valid:
            raise ValueError(
                f"'{new_status}' is not a valid status for {self.__class__.__name__}. "
                f"Valid choices: {sorted(valid)}"
            )
        self.status = new_status
        self.status_changed_at = timezone.now()
        if save:
            self.save(update_fields=["status", "status_changed_at", "updated_at"])
