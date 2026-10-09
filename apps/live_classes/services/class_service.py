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
    LiveClassSchedule,
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
        Creates a master schedule record and a single session instance.
        """
        if start_time >= end_time:
            raise ValidationError("Start time must be strictly before end time.")

        if tutor and tutor.role not in [UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN]:
            raise ValidationError("Assigned user must have Tutor or Admin role.")

        master_schedule = LiveClassSchedule.objects.create(
            title=title.strip(),
            topic=topic.strip(),
            cohort=cohort,
            tutor=tutor,
            schedule_mode="SINGLE",
            days_of_week=[scheduled_date.weekday()],
            start_time=start_time,
            end_time=end_time,
            start_date=scheduled_date,
            end_date=scheduled_date,
            period_months=1,
            period_unit="months",
            google_meet_url=google_meet_url.strip(),
            is_published=is_published,
            notes=notes.strip(),
            created_by=created_by,
        )

        live_class = LiveClass.objects.create(
            title=title.strip(),
            topic=topic.strip(),
            cohort=cohort,
            tutor=tutor,
            schedule=master_schedule,
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
            "Live class scheduled: '%s' on %s (%s - %s), tutor=%s, cohort=%s, schedule=%s",
            live_class.title,
            scheduled_date,
            start_time,
            end_time,
            tutor.phone_number if tutor else "Unassigned",
            cohort.code if cohort else "Open",
            master_schedule.id,
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
        day_of_week: Optional[int] = None,
        days_of_week: Optional[List[int]] = None,
        start_time: time = None,
        end_time: time = None,
        period_months: int = 3,
        period_unit: str = "months",
        end_date: Optional[date] = None,
        google_meet_url: str = "",
        cohort: Optional[Cohort] = None,
        tutor: Optional[User] = None,
        topic: str = "",
        is_published: bool = True,
        notes: str = "",
        created_by: Optional[User] = None,
    ) -> LiveClassSchedule:
        """
        Schedule recurring live classes for specific days of the week over a given period or until end_date.
        Creates a master LiveClassSchedule record and linked LiveClass session occurrences.
        """
        import calendar
        from datetime import timedelta

        if start_time and end_time and start_time >= end_time:
            raise ValidationError("Start time must be strictly before end time.")

        # Determine target weekdays (0=Mon ... 6=Sun)
        target_days = list(days_of_week or [])
        if day_of_week is not None and day_of_week not in target_days:
            target_days.append(day_of_week)
        if not target_days:
            target_days = [start_date.weekday()]

        # Determine period end date
        if end_date:
            period_end_date = end_date
        elif period_unit == "years":
            year = start_date.year + period_months
            max_day = calendar.monthrange(year, start_date.month)[1]
            day = min(start_date.day, max_day)
            period_end_date = date(year, start_date.month, day)
        else:
            year = start_date.year
            month = start_date.month + period_months
            while month > 12:
                year += 1
                month -= 12
            max_day = calendar.monthrange(year, month)[1]
            day = min(start_date.day, max_day)
            period_end_date = date(year, month, day)

        if not google_meet_url:
            meet_slug = f"sifo-{title.lower()[:8].strip().replace(' ', '-')}-live"
            google_meet_url = f"https://meet.google.com/{meet_slug}"

        # 1. Create the single master LiveClassSchedule record
        master_schedule = LiveClassSchedule.objects.create(
            title=title.strip(),
            topic=topic.strip(),
            cohort=cohort,
            tutor=tutor,
            schedule_mode="RECURRING",
            days_of_week=target_days,
            start_time=start_time,
            end_time=end_time,
            start_date=start_date,
            end_date=period_end_date,
            period_months=period_months,
            period_unit=period_unit,
            google_meet_url=google_meet_url.strip(),
            is_published=is_published,
            notes=notes.strip(),
            created_by=created_by,
        )

        # 2. Generate child session instances linked to the master schedule
        created_sessions = []
        cur = start_date
        while cur <= period_end_date:
            if cur.weekday() in target_days:
                session = LiveClass.objects.create(
                    title=title.strip(),
                    topic=topic.strip(),
                    cohort=cohort,
                    tutor=tutor,
                    schedule=master_schedule,
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
            cur += timedelta(days=1)

        logger.info(
            "Created Master Schedule %s with %d child sessions for '%s' (Days %s, until %s)",
            master_schedule.id,
            len(created_sessions),
            title,
            target_days,
            period_end_date,
        )
        return master_schedule

    @classmethod
    @transaction.atomic
    def delete_schedule(cls, schedule_id: str, deleted_by: Optional[User] = None) -> bool:
        """
        Delete a master schedule and soft-delete/cancel all its child live class sessions.
        """
        schedule = LiveClassSchedule.objects.get(id=schedule_id)
        for session in schedule.sessions.all():
            session.delete(deleted_by=deleted_by)
        schedule.delete(deleted_by=deleted_by)
        logger.info("Deleted master schedule %s and associated sessions", schedule_id)
        return True

    @classmethod
    @transaction.atomic
    def update_schedule(
        cls,
        schedule_id: str,
        title: Optional[str] = None,
        topic: Optional[str] = None,
        cohort: Optional[Cohort] = None,
        tutor: Optional[User] = None,
        google_meet_url: Optional[str] = None,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
        is_published: Optional[bool] = None,
        notes: Optional[str] = None,
        updated_by: Optional[User] = None,
    ) -> LiveClassSchedule:
        """
        Update master schedule attributes and synchronize future scheduled session instances.
        """
        schedule = LiveClassSchedule.objects.get(id=schedule_id)
        if title is not None:
            schedule.title = title.strip()
        if topic is not None:
            schedule.topic = topic.strip()
        if cohort is not None:
            schedule.cohort = cohort
        if tutor is not None:
            schedule.tutor = tutor
        if google_meet_url is not None:
            schedule.google_meet_url = google_meet_url.strip()
        if start_time is not None:
            schedule.start_time = start_time
        if end_time is not None:
            schedule.end_time = end_time
        if is_published is not None:
            schedule.is_published = is_published
        if notes is not None:
            schedule.notes = notes.strip()
        schedule.save()

        # Synchronize future sessions
        future_sessions = schedule.sessions.filter(status=LiveClassStatus.SCHEDULED)
        for s in future_sessions:
            if title is not None:
                s.title = schedule.title
            if topic is not None:
                s.topic = schedule.topic
            if cohort is not None:
                s.cohort = schedule.cohort
            if tutor is not None:
                s.tutor = schedule.tutor
            if google_meet_url is not None:
                s.google_meet_url = schedule.google_meet_url
            if start_time is not None:
                s.start_time = schedule.start_time
            if end_time is not None:
                s.end_time = schedule.end_time
            if is_published is not None:
                s.is_published = schedule.is_published
            s.save()

        logger.info("Updated master schedule %s and synced %d future sessions", schedule_id, future_sessions.count())
        return schedule

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
