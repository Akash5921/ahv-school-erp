"""
Seed management command.
Creates a full test dataset: school, session, users for all roles,
classes, sections, subjects, students, staff, designations.

Usage:
    python manage.py seed
    python manage.py seed --fresh   (drops existing test data first)
"""

import datetime
import random

from django.core.management.base import BaseCommand
from django.db import transaction

PASSWORD = 'pass12345'
SCHOOL_NAME = 'Test School'
SESSION_NAME = '2024-25'
SESSION_START = datetime.date(2024, 4, 1)
SESSION_END = datetime.date(2025, 3, 31)


class Command(BaseCommand):
    help = 'Seeds the database with test data.'

    def add_arguments(self, parser):
        parser.add_argument('--fresh', action='store_true',
                            help='Delete existing test school data before seeding.')

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.core.users.models import User
        from apps.core.schools.models import School
        from apps.core.academic_sessions.models import AcademicSession
        from apps.core.academics.models import SchoolClass, Section, Subject, ClassSubject
        from apps.core.students.models import Student, StudentSessionRecord
        from apps.core.hr.models import Designation, Staff

        self.stdout.write('Seeding database...')

        # ── School ───────────────────────────────────────────────────────────
        school, _ = School.objects.get_or_create(
            name=SCHOOL_NAME,
            defaults={
                'address': '123 Main Street, City',
                'phone': '9876543210',
                'email': 'admin@testschool.edu',
                'code': 'TST',
            }
        )
        self.stdout.write(f'  School: {school.name}  (id={school.id})')

        # ── Academic Session ─────────────────────────────────────────────────
        session, _ = AcademicSession.objects.get_or_create(
            school=school,
            name=SESSION_NAME,
            defaults={
                'start_date': SESSION_START,
                'end_date': SESSION_END,
                'is_active': True,
            }
        )
        # Ensure only this session is active
        AcademicSession.objects.filter(school=school).exclude(pk=session.pk).update(is_active=False)
        self.stdout.write(f'  Session: {session.name}  (id={session.id}, active={session.is_active})')

        # ── Users — all roles ─────────────────────────────────────────────────
        users_spec = [
            # username          role             email                        school?
            ('superadmin',      'superadmin',    'superadmin@testschool.edu', None),
            ('principal',       'principal',     'principal@testschool.edu',  school),
            ('schooladmin',     'schooladmin',   'schooladmin@testschool.edu',school),
            ('accountant',      'accountant',    'accountant@testschool.edu', school),
            ('teacher1',        'teacher',       'teacher1@testschool.edu',   school),
            ('teacher2',        'teacher',       'teacher2@testschool.edu',   school),
            ('teacher3',        'teacher',       'teacher3@testschool.edu',   school),
            ('staff1',          'staff',         'staff1@testschool.edu',     school),
            ('parent1',         'parent',        'parent1@testschool.edu',    school),
        ]

        created_users = {}
        for username, role, email, user_school in users_spec:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'role': role,
                    'school': user_school,
                    'first_name': username.capitalize(),
                    'last_name': 'Test',
                }
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            created_users[username] = user
            flag = 'created' if created else 'exists'
            self.stdout.write(f'  User [{flag}]: {username:20s} role={role}')

        # ── Classes ──────────────────────────────────────────────────────────
        classes = {}
        for num in range(1, 11):
            cls, _ = SchoolClass.objects.get_or_create(
                school=school,
                session=session,
                name=f'Class {num}',
                defaults={'display_order': num}
            )
            classes[num] = cls

        self.stdout.write(f'  Classes: {len(classes)} created/verified')

        # ── Sections ─────────────────────────────────────────────────────────
        sections = {}
        for num, cls in classes.items():
            for sec_name in ('A', 'B'):
                sec, _ = Section.objects.get_or_create(
                    school_class=cls,
                    name=sec_name,
                )
                sections[(num, sec_name)] = sec

        self.stdout.write(f'  Sections: {len(sections)} created/verified')

        # ── Subjects ─────────────────────────────────────────────────────────
        subject_names = [
            ('Mathematics', 'MATH'),
            ('Science', 'SCI'),
            ('English', 'ENG'),
            ('Hindi', 'HIN'),
            ('Social Studies', 'SST'),
        ]
        subjects = {}
        for name, code in subject_names:
            subj, _ = Subject.objects.get_or_create(
                school=school,
                name=name,
                defaults={'code': code}
            )
            subjects[code] = subj

        self.stdout.write(f'  Subjects: {len(subjects)} created/verified')

        # ── Class-Subject mappings ────────────────────────────────────────────
        for cls in classes.values():
            for subj in subjects.values():
                ClassSubject.objects.get_or_create(
                    school_class=cls,
                    subject=subj,
                    defaults={'max_marks': 100, 'pass_marks': 33}
                )

        self.stdout.write(f'  Class-Subject mappings: done')

        # ── Designations ─────────────────────────────────────────────────────
        for desig_name in ('Principal', 'Teacher', 'Clerk', 'Peon'):
            Designation.objects.get_or_create(school=school, name=desig_name)

        # ── Staff ─────────────────────────────────────────────────────────────
        teacher_desig = Designation.objects.get(school=school, name='Teacher')
        staff_users = [
            ('teacher1', 'T001', 'John', 'Smith'),
            ('teacher2', 'T002', 'Mary', 'Johnson'),
            ('teacher3', 'T003', 'Robert', 'Brown'),
            ('staff1',   'S001', 'Alice', 'Williams'),
        ]
        for username, emp_id, first, last in staff_users:
            user = created_users[username]
            user.first_name = first
            user.last_name = last
            user.save(update_fields=['first_name', 'last_name'])
            Staff.objects.get_or_create(
                school=school,
                user=user,
                defaults={
                    'employee_id': emp_id,
                    'designation': teacher_desig,
                    'joining_date': datetime.date(2020, 6, 1),
                    'status': 'active',
                }
            )

        self.stdout.write(f'  Staff: 4 created/verified')

        # ── Students ─────────────────────────────────────────────────────────
        student_data = [
            ('2024001', 'Aarav',    'Sharma',   'male',   1, 'A'),
            ('2024002', 'Priya',    'Patel',    'female', 1, 'A'),
            ('2024003', 'Rahul',    'Gupta',    'male',   1, 'B'),
            ('2024004', 'Ananya',   'Singh',    'female', 1, 'B'),
            ('2024005', 'Vikram',   'Kumar',    'male',   2, 'A'),
            ('2024006', 'Sneha',    'Verma',    'female', 2, 'A'),
            ('2024007', 'Arjun',    'Mehta',    'male',   2, 'B'),
            ('2024008', 'Kavya',    'Joshi',    'female', 3, 'A'),
            ('2024009', 'Rohan',    'Nair',     'male',   3, 'A'),
            ('2024010', 'Ishaan',   'Reddy',    'male',   3, 'B'),
            ('2024011', 'Divya',    'Rao',      'female', 4, 'A'),
            ('2024012', 'Siddharth','Bose',     'male',   4, 'A'),
            ('2024013', 'Aisha',    'Khan',     'female', 4, 'B'),
            ('2024014', 'Aditya',   'Mishra',   'male',   5, 'A'),
            ('2024015', 'Pooja',    'Iyer',     'female', 5, 'A'),
        ]

        for adm_no, first, last, gender, class_num, sec_name in student_data:
            student, created = Student.objects.get_or_create(
                school=school,
                admission_number=adm_no,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'gender': gender,
                    'date_of_birth': datetime.date(2010, random.randint(1, 12), random.randint(1, 28)),
                    'admission_type': 'fresh',
                    'status': 'active',
                    'session': session,
                    'current_class': classes[class_num],
                    'current_section': sections[(class_num, sec_name)],
                }
            )
            if created:
                StudentSessionRecord.objects.get_or_create(
                    school=school,
                    student=student,
                    session=session,
                    defaults={
                        'school_class': classes[class_num],
                        'section': sections[(class_num, sec_name)],
                        'roll_number': adm_no[-3:],
                    }
                )

        self.stdout.write(f'  Students: {len(student_data)} created/verified')

        # ── Summary ──────────────────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('Database seeding complete!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'  School  : {school.name}')
        self.stdout.write(f'  Session : {session.name} ({SESSION_START} to {SESSION_END})')
        self.stdout.write('')
        self.stdout.write('  LOGIN CREDENTIALS (all passwords = pass12345)')
        self.stdout.write('  ' + '-' * 52)
        self.stdout.write(f'  {"Username":<22} {"Role":<15} {"Access":<15}')
        self.stdout.write('  ' + '-' * 52)
        rows = [
            ('superadmin',  'superadmin',  'All schools'),
            ('principal',   'principal',   'Test School'),
            ('schooladmin', 'schooladmin', 'Test School'),
            ('accountant',  'accountant',  'Test School'),
            ('teacher1',    'teacher',     'Test School'),
            ('teacher2',    'teacher',     'Test School'),
            ('teacher3',    'teacher',     'Test School'),
            ('staff1',      'staff',       'Test School'),
            ('parent1',     'parent',      'Test School'),
        ]
        for u, r, a in rows:
            self.stdout.write(f'  {u:<22} {r:<15} {a:<15}')
        self.stdout.write('  ' + '-' * 52)
        self.stdout.write(f'  Password for all: {PASSWORD}')
        self.stdout.write(self.style.SUCCESS('=' * 60))
