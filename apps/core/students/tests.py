import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import ClassSubject, SchoolClass, Section, Subject
from apps.core.schools.models import School

from .models import (
    DocumentType,
    Parent,
    Student,
    StudentDocument,
    StudentSessionRecord,
    StudentStatusHistory,
    StudentSubject,
)
from .services import (
    change_student_status,
    finalize_admission,
    generate_id_card_pdf,
    generate_transfer_certificate_pdf,
    sync_student_academic_links,
)


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='students_core_tests_')


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class StudentLifecycleModelTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.school = School.objects.create(name='Student School', code='student_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='8th',
            code='VIII',
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A')

    def _create_student(self, admission_number='S001', roll='1'):
        return Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number=admission_number,
            first_name='Ayan',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number=roll,
        )

    def test_admission_number_unique_per_school(self):
        self._create_student(admission_number='ADM-100')
        with self.assertRaises(IntegrityError):
            self._create_student(admission_number='ADM-100', roll='2')

    def test_roll_number_unique_within_class_section_session(self):
        self._create_student(admission_number='ADM-101', roll='10')
        with self.assertRaises(IntegrityError):
            self._create_student(admission_number='ADM-102', roll='10')

    def test_transfer_admission_requires_previous_school_name(self):
        student = Student(
            school=self.school,
            session=self.session,
            admission_number='ADM-200',
            first_name='Riya',
            admission_type=Student.ADMISSION_TRANSFER,
            current_class=self.school_class,
            current_section=self.section,
        )
        with self.assertRaises(ValidationError):
            student.full_clean()

    def test_soft_delete_archives_student(self):
        student = self._create_student(admission_number='ADM-300')
        student.delete()
        student.refresh_from_db()

        self.assertFalse(student.is_active)
        self.assertTrue(student.is_archived)
        self.assertEqual(student.status, Student.STATUS_ALUMNI)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class StudentLifecycleServiceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        user_model = get_user_model()

        self.school = School.objects.create(name='Service School', code='service_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='10th',
            code='X',
        )
        self.section = Section.objects.create(school_class=self.school_class, name='A')

        self.math = Subject.objects.create(school=self.school, name='Math', code='MTH')
        self.science = Subject.objects.create(school=self.school, name='Science', code='SCI')
        ClassSubject.objects.create(school_class=self.school_class, subject=self.math)
        ClassSubject.objects.create(school_class=self.school_class, subject=self.science)

        self.admin = user_model.objects.create_user(
            username='service_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )

        self.student = Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number='ADM-500',
            first_name='Kabir',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number='15',
        )

    def test_sync_student_links_creates_subjects_and_session_record(self):
        sync_student_academic_links(self.student)

        self.assertEqual(StudentSubject.objects.filter(student=self.student, session=self.session).count(), 2)
        self.assertTrue(
            StudentSessionRecord.objects.filter(
                student=self.student,
                session=self.session,
                school_class=self.school_class,
                section=self.section,
                is_current=True,
            ).exists()
        )

    def test_finalize_admission_requires_approved_mandatory_documents(self):
        doc_type = DocumentType.objects.create(
            school=self.school,
            name='Birth Certificate',
            required_for=DocumentType.FOR_FRESH,
            is_mandatory=True,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            finalize_admission(self.student, finalized_by=self.admin)

        StudentDocument.objects.create(
            student=self.student,
            document_type=doc_type,
            file=SimpleUploadedFile('birth.pdf', b'pdf-content', content_type='application/pdf'),
            status=StudentDocument.STATUS_APPROVED,
            verified_by=self.admin,
        )
        finalize_admission(self.student, finalized_by=self.admin)

        self.student.refresh_from_db()
        self.assertTrue(self.student.admission_finalized)

    def test_change_status_creates_history(self):
        change_student_status(
            student=self.student,
            new_status=Student.STATUS_TRANSFERRED,
            changed_by=self.admin,
            reason='Transfer requested',
        )

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, Student.STATUS_TRANSFERRED)
        self.assertFalse(self.student.is_active)
        self.assertTrue(StudentStatusHistory.objects.filter(student=self.student).exists())

    def test_generate_id_card_pdf(self):
        pdf_bytes = generate_id_card_pdf(self.student, include_qr=True)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_transfer_certificate_requires_transferred_status(self):
        with self.assertRaises(ValidationError):
            generate_transfer_certificate_pdf(self.student)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class StudentLifecycleViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        user_model = get_user_model()

        self.school = School.objects.create(name='View School', code='view_school')
        self.session = AcademicSession.objects.create(
            school=self.school,
            name='2026-27',
            start_date='2026-04-01',
            end_date='2027-03-31',
            is_active=True,
        )
        self.school.current_session = self.session
        self.school.save(update_fields=['current_session'])

        self.school_class = SchoolClass.objects.create(
            school=self.school,
            session=self.session,
            name='7th',
            code='VII',
        )
        self.section = Section.objects.create(school_class=self.school_class, name='B')

        self.subject = Subject.objects.create(school=self.school, name='English', code='ENG')
        ClassSubject.objects.create(school_class=self.school_class, subject=self.subject)

        self.document_type = DocumentType.objects.create(
            school=self.school,
            name='Birth Certificate',
            required_for=DocumentType.FOR_BOTH,
            is_mandatory=True,
            is_active=True,
        )

        self.admin = user_model.objects.create_user(
            username='view_admin',
            password='pass12345',
            role='schooladmin',
            school=self.school,
        )
        self.teacher = user_model.objects.create_user(
            username='view_teacher',
            password='pass12345',
            role='teacher',
            school=self.school,
        )

    def _create_student(self, admission_number='ADM-V-1'):
        return Student.objects.create(
            school=self.school,
            session=self.session,
            admission_number=admission_number,
            first_name='Meera',
            admission_type=Student.ADMISSION_FRESH,
            current_class=self.school_class,
            current_section=self.section,
            roll_number=admission_number.split('-')[-1],
        )

    def test_school_admin_can_create_student_and_auto_map_subjects(self):
        self.client.login(username='view_admin', password='pass12345')

        response = self.client.post(reverse('student_create'), {
            'session': self.session.id,
            'admission_number': 'ADM-V-100',
            'first_name': 'Arjun',
            'last_name': 'K',
            'gender': 'male',
            'admission_date': '2026-04-10',
            'admission_type': Student.ADMISSION_FRESH,
            'current_class': self.school_class.id,
            'current_section': self.section.id,
            'roll_number': '11',
            'parent-father_name': 'Rajesh',
            'parent-phone': '9999999999',
            'parent-email': 'parent@example.com',
        })

        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(school=self.school, admission_number='ADM-V-100')

        self.assertTrue(Parent.objects.filter(student=student).exists())
        self.assertTrue(StudentSubject.objects.filter(student=student, subject=self.subject).exists())

    def test_document_workflow_and_admission_finalization(self):
        self.client.login(username='view_admin', password='pass12345')
        student = self._create_student('ADM-V-200')

        upload_response = self.client.post(
            reverse('student_document_list', args=[student.id]),
            {
                'document_type': self.document_type.id,
                'file': SimpleUploadedFile('doc.pdf', b'pdf', content_type='application/pdf'),
                'remarks': 'Initial upload',
            },
        )
        self.assertEqual(upload_response.status_code, 302)

        document = StudentDocument.objects.get(student=student, document_type=self.document_type)

        verify_response = self.client.post(
            reverse('student_document_verify', args=[student.id, document.id]),
            {'status': StudentDocument.STATUS_APPROVED, 'remarks': 'Verified'},
        )
        self.assertEqual(verify_response.status_code, 302)

        finalize_response = self.client.post(reverse('student_finalize_admission', args=[student.id]))
        self.assertEqual(finalize_response.status_code, 302)

        student.refresh_from_db()
        self.assertTrue(student.admission_finalized)

    def test_bulk_id_card_download_returns_pdf(self):
        self.client.login(username='view_admin', password='pass12345')
        self._create_student('ADM-V-300')

        response = self.client.get(reverse('student_id_card_bulk_download'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/pdf', response['Content-Type'])

    def test_teacher_cannot_access_student_lifecycle_pages(self):
        self.client.login(username='view_teacher', password='pass12345')
        response = self.client.get(reverse('student_list'))
        self.assertEqual(response.status_code, 403)
