
import random
from django.core.management.base import BaseCommand
from faker import Faker
from django.db import transaction

from apps.core.schools.models import School
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.academics.students.models import Student
from apps.academics.staff.models import Staff
from apps.core.users.models import User

class Command(BaseCommand):
    help = 'Seeds the database with test data.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')

        fake = Faker()

        # Create a school
        school, created = School.objects.get_or_create(
            name=fake.company() + " School",
            defaults={
                'address': fake.address(),
                'phone': fake.phone_number(),
                'email': fake.email(),
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Successfully created school: {school.name}'))

        # Create an academic session
        academic_session, created = AcademicSession.objects.get_or_create(
            school=school,
            name='2024-25',
            defaults={
                'start_date': '2024-04-01',
                'end_date': '2025-03-31',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Successfully created academic session: {academic_session.name}'))
        
        school.current_session = academic_session
        school.save()


        # Create users
        if not User.objects.filter(username='superadmin').exists():
            User.objects.create_superuser('superadmin', 'superadmin@example.com', 'password', role='superadmin')
            self.stdout.write(self.style.SUCCESS('Successfully created superadmin user.'))

        school_admin, created = User.objects.get_or_create(
            username='schooladmin',
            defaults={
                'role': 'schooladmin',
                'school': school,
            }
        )
        if created:
            school_admin.set_password('password')
            school_admin.save()
            self.stdout.write(self.style.SUCCESS('Successfully created schooladmin user.'))

        # Create classes
        for i in range(1, 11):
            school_class, created = SchoolClass.objects.get_or_create(
                school=school,
                name=f'Class {i}',
                defaults={'order': i}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created class: {school_class.name}'))

                # Create sections
                for section_name in ['A', 'B']:
                    section, created = Section.objects.get_or_create(
                        school_class=school_class,
                        name=section_name
                    )
                    if created:
                        self.stdout.write(self.style.SUCCESS(f'  - Successfully created section: {section.name}'))

        # Create subjects
        for school_class in SchoolClass.objects.filter(school=school):
            for subject_name in ['English', 'Math', 'Science', 'Social Studies', 'Hindi']:
                subject, created = Subject.objects.get_or_create(
                    school=school,
                    school_class=school_class,
                    name=subject_name
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Successfully created subject: {subject.name} for {school_class.name}'))

        # Create students
        for school_class in SchoolClass.objects.filter(school=school):
            for section in school_class.sections.all():
                for _ in range(20):
                    first_name = fake.first_name()
                    last_name = fake.last_name()
                    student, created = Student.objects.get_or_create(
                        school=school,
                        admission_number=fake.unique.random_number(digits=6),
                        defaults={
                            'first_name': first_name,
                            'last_name': last_name,
                            'date_of_birth': fake.date_of_birth(minimum_age=5, maximum_age=15),
                            'gender': random.choice(['male', 'female']),
                            'academic_session': academic_session,
                            'school_class': school_class,
                            'section': section,
                        }
                    )
                    if created:
                        self.stdout.write(self.style.SUCCESS(f'Successfully created student: {student.name}'))

        # Create staff
        for staff_type in ['teacher', 'accountant', 'office']:
            for _ in range(5):
                first_name = fake.first_name()
                last_name = fake.last_name()
                staff, created = Staff.objects.get_or_create(
                    school=school,
                    staff_id=fake.unique.random_number(digits=5),
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'staff_type': staff_type,
                        'joining_date': fake.date_this_decade(),
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Successfully created staff: {staff.name}'))

        self.stdout.write(self.style.SUCCESS('Database seeding complete!'))
