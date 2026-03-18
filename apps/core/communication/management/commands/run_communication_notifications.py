from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School

from ...services import run_fee_overdue_notifications


class Command(BaseCommand):
    help = 'Run fee overdue communication notifications for one or more schools.'

    def add_arguments(self, parser):
        parser.add_argument('--school-code', type=str, help='Optional school code filter.')
        parser.add_argument('--session-id', type=int, help='Optional session id override.')
        parser.add_argument('--date', type=str, help='Optional as-of date in YYYY-MM-DD format.')

    def handle(self, *args, **options):
        school_code = options.get('school_code')
        session_id = options.get('session_id')
        as_of_date_raw = options.get('date')

        as_of_date = timezone.localdate()
        if as_of_date_raw:
            parsed = parse_date(as_of_date_raw)
            if not parsed:
                raise CommandError('Invalid --date value. Use YYYY-MM-DD.')
            as_of_date = parsed

        schools = School.objects.filter(is_active=True)
        if school_code:
            schools = schools.filter(code=school_code)
            if not schools.exists():
                raise CommandError(f'No active school found for code={school_code}.')

        total_students = 0
        total_notifications = 0

        for school in schools.order_by('name'):
            session = None
            if session_id:
                session = AcademicSession.objects.filter(pk=session_id, school=school).first()
                if not session:
                    self.stdout.write(self.style.WARNING(
                        f'Skipping {school.code}: session {session_id} does not belong to school.'
                    ))
                    continue

            result = run_fee_overdue_notifications(
                school=school,
                session=session,
                as_of_date=as_of_date,
            )

            total_students += result['students']
            total_notifications += result['notifications']

            self.stdout.write(
                self.style.SUCCESS(
                    f"{school.code}: students_with_due={result['students']}, notifications={result['notifications']}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Total students with dues: {total_students}, total notifications: {total_notifications}'
            )
        )
