from datetime import date, time
import logging
from typing import List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.notifications.services import NotificationService
from apps.live_classes.models import (
    ClassResource,
    Cohort,
    LiveClass,
    LiveClassStatus,
)

logger = logging.getLogger("apps.live_classes.services")


class LiveClassService:
    """
    Business service managing live class scheduling, Google Meet integration,
    session lifecycle (scheduled -> in progress -> completed), and reminders.
    """

    @classmethod
    @transaction.atomic
    def schedule_class(
        cls,
        title: str,
        scheduled_date: date,
        start_time: time,
        end_time: time,
        google_meet_url: str,
        topic: str = "",
        cohort: Optional[Cohort] = None,
        tutor: Optional[User] = None,
        module=None,
        lesson=None,
        notes: str = "",
        is_published: bool = True,
        created_by: Optional[User] = None,
    ) -> LiveClass:
        """
        Schedule a new live class session.
        Validates schedule boundaries and dispatches scheduled notifications.
        """
        if start_time >= end_time:
            raise ValidationError("Start time must be strictly before end time.")

        if tutor and tutor.role not in [UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN]:
            raise ValidationError("Assigned user must have Tutor or Admin role.")

        live_class = LiveClass.objects.create(
            title=title.strip(),
            topic=topic.strip(),
            cohort=cohort,
            tutor=tutor,
            module=module,
            lesson=lesson,
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            google_meet_url=google_meet_url.strip(),
            status=LiveClassStatus.SCHEDULED,
            is_published=is_published,
            notes=notes.strip(),
            created_by=created_by,
        )

        logger.info(
            "Live class scheduled: '%s' on %s (%s - %s), tutor=%s, cohort=%s",
            live_class.title,
            scheduled_date,
            start_time,
            end_time,
            tutor.phone_number if tutor else "Unassigned",
            cohort.code if cohort else "Open",
        )

        if is_published:
            cls.notify_students_scheduled(live_class)

        return live_class

    @classmethod
    @transaction.atomic
    def schedule_recurring_classes(
        cls,
        title: str,
        start_date: date,
        day_of_week: int,
        start_time: time,
        end_time: time,
        period_months: int = 3,
        google_meet_url: str = "",
        cohort: Optional[Cohort] = None,
        tutor: Optional[User] = None,
        topic: str = "",
        is_published: bool = True,
        notes: str = "",
        created_by: Optional[User] = None,
    ) -> List[LiveClass]:
        """
        Schedule recurring live classes for a specific day of the week over a given period in months.
        E.g. each Tuesday 2pm for 3 months.
        """
        import calendar
        from datetime import timedelta

        if start_time >= end_time:
            raise ValidationError("Start time must be strictly before end time.")

        # Calculate approximate end date based on period_months
        year = start_date.year
        month = start_date.month + period_months
        while month > 12:
            year += 1
            month -= 12
        max_day = calendar.monthrange(year, month)[1]
        day = min(start_date.day, max_day)
        period_end_date = date(year, month, day)

        # Advance to first occurrence of day_of_week
        cur = start_date
        days_ahead = (day_of_week - cur.weekday()) % 7
        cur = cur + timedelta(days=days_ahead)

        if not google_meet_url:
            meet_slug = f"sifo-{title.lower()[:8].strip().replace(' ', '-')}-{calendar.day_abbr[day_of_week].lower()}"
            google_meet_url = f"https://meet.google.com/{meet_slug}"

        created_sessions = []
        while cur <= period_end_date:
            session = LiveClass.objects.create(
                title=title.strip(),
                topic=topic.strip(),
                cohort=cohort,
                tutor=tutor,
                scheduled_date=cur,
                start_time=start_time,
                end_time=end_time,
                google_meet_url=google_meet_url.strip(),
                status=LiveClassStatus.SCHEDULED,
                is_published=is_published,
                notes=notes.strip(),
                created_by=created_by,
            )
            created_sessions.append(session)
            cur += timedelta(days=7)

        logger.info(
            "Scheduled %d recurring classes for '%s' (Day %d, %d months)",
            len(created_sessions),
            title,
            day_of_week,
            period_months,
        )
        return created_sessions

    @classmethod
    @transaction.atomic
    def reschedule_class(
        cls,
        live_class: LiveClass,
        new_date: date,
        new_start_time: time,
        new_end_time: time,
        reason: str = "",
    ) -> LiveClass:
        """Reschedule date/time for an upcoming class and notify enrolled students."""
        if new_start_time >= new_end_time:
            raise ValidationError("Start time must precede end time.")

        if live_class.status == LiveClassStatus.COMPLETED:
            raise ValidationError("Cannot reschedule a session that has already completed.")

        live_class.scheduled_date = new_date
        live_class.start_time = new_start_time
        live_class.end_time = new_end_time
        live_class.status = LiveClassStatus.RESCHEDULED
        if reason:
            prefix = f"\n[Rescheduled: {reason}]"
            live_class.notes = (live_class.notes + prefix).strip()
        live_class.save()

        logger.info("Live class %s rescheduled to %s %s", live_class.id, new_date, new_start_time)
        cls.notify_students_scheduled(live_class, is_reschedule=True)
        return live_class

    @classmethod
    @transaction.atomic
    def start_session(cls, live_class: LiveClass, tutor: Optional[User] = None) -> LiveClass:
        """
        Transition session to IN_PROGRESS when tutor joins/starts the session.
        Can send SMS reminder with Meet link to students starting right now.
        """
        if live_class.status == LiveClassStatus.COMPLETED:
            raise ValidationError("This class has already ended.")

        live_class.start_session()
        logger.info("Live session started: %s (id=%s)", live_class.title, live_class.id)

        # Dispatch immediate SMS reminder with meet link
        cls.notify_students_reminder(live_class)
        return live_class

    @classmethod
    @transaction.atomic
    def end_session(
        cls,
        live_class: LiveClass,
        recording_url: str = "",
        tutor: Optional[User] = None,
    ) -> LiveClass:
        """Mark session as COMPLETED and save recording URL if available."""
        live_class.end_session(recording_url=recording_url)
        logger.info("Live session ended: %s (recording=%s)", live_class.title, bool(recording_url))
        return live_class

    @classmethod
    @transaction.atomic
    def cancel_class(cls, live_class: LiveClass, reason: str = "") -> LiveClass:
        """Cancel a scheduled class."""
        if live_class.status == LiveClassStatus.COMPLETED:
            raise ValidationError("Cannot cancel an already completed session.")

        live_class.status = LiveClassStatus.CANCELLED
        if reason:
            live_class.notes = (live_class.notes + f"\n[Cancelled: {reason}]").strip()
        live_class.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Live class cancelled: %s (reason: %s)", live_class.id, reason)
        return live_class

    @classmethod
    def add_resource(
        cls,
        live_class: LiveClass,
        title: str,
        file=None,
        external_link: str = "",
        description: str = "",
        uploaded_by: Optional[User] = None,
    ) -> ClassResource:
        """Attach a slide deck, worksheet, or reference material to a live class."""
        if not file and not external_link:
            raise ValidationError("Either a file or an external URL link must be provided.")

        resource = ClassResource.objects.create(
            live_class=live_class,
            title=title.strip(),
            file=file,
            external_link=external_link.strip(),
            description=description.strip(),
            uploaded_by=uploaded_by,
        )
        logger.info("Class resource added to %s: '%s'", live_class.id, resource.title)
        return resource

    @classmethod
    def notify_students_scheduled(cls, live_class: LiveClass, is_reschedule: bool = False) -> int:
        """Dispatch notifications to students in the cohort or platform-wide."""
        if live_class.cohort:
            recipients = live_class.cohort.students.filter(is_active=True)
        else:
            recipients = User.objects.filter(role=UserRole.STUDENT, is_active=True)

        class_time_str = f"{live_class.scheduled_date.strftime('%d/%m/%Y')} at {live_class.start_time.strftime('%H:%M')}"
        tutor_name = (
            live_class.tutor.get_full_name() or live_class.tutor.phone_number
            if live_class.tutor
            else "Sifo Drive Tutor"
        )
        title_text = f"Live Class {'Rescheduled' if is_reschedule else 'Scheduled'}: {live_class.title}"

        count = 0
        for student in recipients:
            try:
                NotificationService.send_live_class_scheduled(
                    user=student,
                    title=title_text,
                    class_time=class_time_str,
                    tutor_name=tutor_name,
                    live_class_id=str(live_class.id),
                    language="rw",
                )
                count += 1
            except Exception as exc:
                logger.warning("Failed to dispatch live class notice to %s: %s", student.id, exc)

        logger.info("Dispatched live class schedule notice to %d students", count)
        return count

    @classmethod
    def notify_students_reminder(cls, live_class: LiveClass) -> int:
        """Dispatch SMS reminder with Google Meet link to students."""
        if not live_class.google_meet_url:
            return 0

        if live_class.cohort:
            recipients = live_class.cohort.students.filter(is_active=True)
        else:
            recipients = User.objects.filter(role=UserRole.STUDENT, is_active=True)

        count = 0
        for student in recipients:
            try:
                NotificationService.send_live_class_reminder(
                    user=student,
                    meet_link=live_class.google_meet_url,
                    live_class_id=str(live_class.id),
                    language="rw",
                )
                count += 1
            except Exception as exc:
                logger.warning("Failed to dispatch live class SMS reminder to %s: %s", student.id, exc)

        logger.info("Dispatched live class Meet reminder to %d students", count)
        return count
