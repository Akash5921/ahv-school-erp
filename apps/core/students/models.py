from io import BytesIO

from PIL import Image, ImageDraw, ImageOps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject
from apps.core.schools.models import School
from apps.core.utils.managers import SchoolManager


class Student(models.Model):
    ADMISSION_FRESH = 'fresh'
    ADMISSION_TRANSFER = 'transfer'
    ADMISSION_TYPE_CHOICES = (
        (ADMISSION_FRESH, 'Fresh'),
        (ADMISSION_TRANSFER, 'Transfer'),
    )

    STATUS_ACTIVE = 'active'
    STATUS_TRANSFERRED = 'transferred'
    STATUS_PASSED = 'passed'
    STATUS_DROPPED = 'dropped'
    STATUS_ALUMNI = 'alumni'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_TRANSFERRED, 'Transferred'),
        (STATUS_PASSED, 'Passed'),
        (STATUS_DROPPED, 'Dropped'),
        (STATUS_ALUMNI, 'Alumni'),
    )

    GENDER_CHOICES = (
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    )
    BLOOD_GROUP_CHOICES = (
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='students_core')
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='students_core')
    objects = SchoolManager()

    admission_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True)
    admission_date = models.DateField(default=timezone.now)
    admission_type = models.CharField(max_length=20, choices=ADMISSION_TYPE_CHOICES, default=ADMISSION_FRESH)
    previous_school_name = models.CharField(max_length=255, blank=True)

    current_class = models.ForeignKey(
        SchoolClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students_core',
    )
    current_section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students_core',
    )
    roll_number = models.CharField(max_length=20, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    photo = models.ImageField(upload_to='students/photos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_reason = models.CharField(max_length=255, blank=True)

    admission_finalized = models.BooleanField(default=False)
    admission_finalized_at = models.DateTimeField(null=True, blank=True)
    admission_finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admission_finalized_students',
    )

    allergies = models.CharField(max_length=255, blank=True)
    medical_conditions = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    doctor_name = models.CharField(max_length=120, blank=True)

    transport_assigned = models.BooleanField(default=False)
    hostel_assigned = models.BooleanField(default=False)
    house = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['admission_number', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'admission_number'],
                name='unique_student_admission_number_per_school',
            ),
            models.UniqueConstraint(
                fields=['school', 'session', 'current_class', 'current_section', 'roll_number'],
                condition=Q(roll_number__isnull=False),
                name='unique_roll_in_class_section_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'status']),
            models.Index(fields=['school', 'is_active']),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def clean(self):
        super().clean()
        if self.session_id and self.school_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Selected session does not belong to your school.'})

        if self.current_class_id:
            if self.current_class.school_id != self.school_id:
                raise ValidationError({'current_class': 'Selected class does not belong to your school.'})
            if self.current_class.session_id != self.session_id:
                raise ValidationError({'current_class': 'Selected class does not belong to the selected session.'})

        if self.current_section_id:
            if not self.current_class_id:
                raise ValidationError({'current_section': 'Select class before section.'})
            if self.current_section.school_class_id != self.current_class_id:
                raise ValidationError({'current_section': 'Selected section does not belong to selected class.'})

        if self.admission_type == self.ADMISSION_TRANSFER and not self.previous_school_name.strip():
            raise ValidationError({'previous_school_name': 'Previous school is required for transfer admission.'})

        if self.roll_number == '':
            self.roll_number = None

    def delete(self, *args, **kwargs):
        if self.is_archived:
            return
        self.is_active = False
        self.is_archived = True
        self.status = self.STATUS_ALUMNI
        self.archived_at = timezone.now()
        self.save(update_fields=['is_active', 'is_archived', 'status', 'archived_at'])

    def __str__(self):
        return f"{self.admission_number} - {self.full_name}"


class Parent(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='parent_info')
    father_name = models.CharField(max_length=120, blank=True)
    mother_name = models.CharField(max_length=120, blank=True)
    guardian_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Parent: {self.guardian_name or self.father_name or self.student.full_name}"


class DocumentType(models.Model):
    FOR_FRESH = Student.ADMISSION_FRESH
    FOR_TRANSFER = Student.ADMISSION_TRANSFER
    FOR_BOTH = 'both'
    REQUIRED_FOR_CHOICES = (
        (FOR_FRESH, 'Fresh'),
        (FOR_TRANSFER, 'Transfer'),
        (FOR_BOTH, 'Both'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='document_types')
    objects = SchoolManager()

    name = models.CharField(max_length=120)
    required_for = models.CharField(max_length=20, choices=REQUIRED_FOR_CHOICES, default=FOR_BOTH)
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name'],
                name='unique_document_type_name_per_school',
            )
        ]

    def __str__(self):
        return self.name


class StudentDocument(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='documents')
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE, related_name='student_documents')
    file = models.FileField(upload_to='students/documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_student_documents',
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-uploaded_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'document_type'],
                name='unique_document_type_per_student',
            )
        ]

    def clean(self):
        super().clean()
        if self.document_type_id and self.student_id:
            if self.document_type.school_id != self.student.school_id:
                raise ValidationError({'document_type': 'Document type must belong to student school.'})

    def __str__(self):
        return f"{self.student.admission_number} - {self.document_type.name}"


class StudentSubject(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='student_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='student_subjects')
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='student_subjects')
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='student_subjects')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['subject__name']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'subject', 'session'],
                name='unique_student_subject_per_session',
            )
        ]

    def clean(self):
        super().clean()
        if self.student_id and self.session_id and self.student.session_id != self.session_id:
            raise ValidationError({'session': 'Student session mismatch.'})
        if self.student_id and self.school_class_id and self.student.current_class_id and self.student.current_class_id != self.school_class_id:
            raise ValidationError({'school_class': 'Class mismatch for student.'})
        if self.subject_id and self.student_id and self.subject.school_id != self.student.school_id:
            raise ValidationError({'subject': 'Subject school mismatch.'})

    def __str__(self):
        return f"{self.student.admission_number} - {self.subject.code}"


class StudentStatusHistory(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=20, choices=Student.STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=Student.STATUS_CHOICES)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_status_changes',
    )
    reason = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.student.admission_number}: {self.old_status} -> {self.new_status}"


class StudentSessionRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='session_records')
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='student_session_records')
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='student_session_records')
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='student_session_records')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='student_session_records')
    roll_number = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Student.STATUS_CHOICES, default=Student.STATUS_ACTIVE)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-session__start_date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['student', 'session'], name='unique_student_record_per_session'),
            models.UniqueConstraint(
                fields=['school', 'session', 'school_class', 'section', 'roll_number'],
                condition=Q(roll_number__isnull=False),
                name='unique_roll_per_section_in_session_records',
            ),
        ]

    def __str__(self):
        return f"{self.student.admission_number} - {self.session.name}"


def image_to_pdf_bytes(images):
    if not images:
        return b''
    rgb_images = [img.convert('RGB') for img in images]
    output = BytesIO()
    rgb_images[0].save(output, format='PDF', save_all=True, append_images=rgb_images[1:])
    return output.getvalue()


def build_id_card_image(student, include_qr=False):
    card = Image.new('RGB', (1000, 600), color='white')
    draw = ImageDraw.Draw(card)
    draw.rectangle([(0, 0), (1000, 90)], fill=(37, 99, 235))
    draw.text((24, 30), student.school.name, fill='white')
    draw.text((24, 112), f"Name: {student.full_name}", fill='black')
    draw.text((24, 160), f"Admission No: {student.admission_number}", fill='black')
    draw.text((24, 208), f"Class: {student.current_class.name if student.current_class else '-'}", fill='black')
    draw.text((24, 256), f"Section: {student.current_section.name if student.current_section else '-'}", fill='black')
    draw.text((24, 304), f"Session: {student.session.name}", fill='black')

    if student.photo:
        try:
            with student.photo.open('rb') as photo_file:
                photo = Image.open(photo_file).convert('RGB')
                photo = ImageOps.fit(photo, (220, 260))
                card.paste(photo, (740, 130))
        except Exception:
            draw.rectangle([(740, 130), (960, 390)], outline='black')
            draw.text((760, 250), "PHOTO", fill='black')
    else:
        draw.rectangle([(740, 130), (960, 390)], outline='black')
        draw.text((760, 250), "PHOTO", fill='black')

    school_logo = getattr(student.school, 'logo', None)
    if school_logo:
        try:
            with school_logo.open('rb') as logo_file:
                logo = Image.open(logo_file).convert('RGBA')
                logo = ImageOps.contain(logo, (120, 70))
                card.paste(logo, (860, 10), mask=logo if logo.mode == 'RGBA' else None)
        except Exception:
            pass

    if include_qr:
        draw.rectangle([(740, 430), (900, 590)], outline='black')
        draw.text((750, 500), f"ID:{student.id}", fill='black')

    return card
