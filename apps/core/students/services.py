from __future__ import annotations

from typing import Iterable

from PIL import Image, ImageDraw, ImageOps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.academics.models import ClassSubject

from .models import (
    DocumentType,
    Student,
    StudentSessionRecord,
    StudentStatusHistory,
    StudentSubject,
    image_to_pdf_bytes,
)


def get_required_document_types(student: Student):
    required_for = [DocumentType.FOR_BOTH, student.admission_type]
    return DocumentType.objects.filter(
        school=student.school,
        is_active=True,
        is_mandatory=True,
        required_for__in=required_for,
    ).order_by('name')


def get_missing_required_documents(student: Student):
    required_ids = list(get_required_document_types(student).values_list('id', flat=True))
    approved_ids = set(
        student.documents.filter(status='approved').values_list('document_type_id', flat=True)
    )
    return [doc_id for doc_id in required_ids if doc_id not in approved_ids]


@transaction.atomic
def sync_student_subjects(student: Student) -> int:
    """Align student subjects with active class-subject mappings for student's class/session."""
    if not student.current_class_id or not student.session_id:
        StudentSubject.objects.filter(student=student, session=student.session).update(is_active=False)
        return 0

    mappings = ClassSubject.objects.filter(
        school_class=student.current_class,
        subject__is_active=True,
    ).select_related('subject')
    mapped_subject_ids = set(mappings.values_list('subject_id', flat=True))

    existing_subjects = {
        obj.subject_id: obj
        for obj in StudentSubject.objects.filter(student=student, session=student.session)
    }

    to_create = []
    for mapping in mappings:
        existing = existing_subjects.get(mapping.subject_id)
        if existing:
            updates = []
            if existing.school_class_id != student.current_class_id:
                existing.school_class = student.current_class
                updates.append('school_class')
            if not existing.is_active:
                existing.is_active = True
                updates.append('is_active')
            if updates:
                existing.save(update_fields=updates)
        else:
            to_create.append(
                StudentSubject(
                    student=student,
                    subject=mapping.subject,
                    school_class=student.current_class,
                    session=student.session,
                    is_active=True,
                )
            )

    if to_create:
        StudentSubject.objects.bulk_create(to_create)

    stale_ids = [
        row.id
        for row in existing_subjects.values()
        if row.subject_id not in mapped_subject_ids and row.is_active
    ]
    if stale_ids:
        StudentSubject.objects.filter(id__in=stale_ids).update(is_active=False)

    return len(mapped_subject_ids)


@transaction.atomic
def sync_student_session_record(student: Student):
    """Maintain one current assignment row per student session for promotion readiness."""
    if not (student.school_id and student.session_id and student.current_class_id and student.current_section_id):
        StudentSessionRecord.objects.filter(student=student, is_current=True).update(is_current=False)
        return None

    StudentSessionRecord.objects.filter(student=student, is_current=True).exclude(
        session=student.session
    ).update(is_current=False)

    record, created = StudentSessionRecord.objects.update_or_create(
        student=student,
        session=student.session,
        defaults={
            'school': student.school,
            'school_class': student.current_class,
            'section': student.current_section,
            'roll_number': student.roll_number,
            'status': student.status,
            'is_current': True,
        },
    )
    if not created and not record.is_current:
        record.is_current = True
        record.save(update_fields=['is_current'])
    return record


@transaction.atomic
def sync_student_academic_links(student: Student) -> None:
    sync_student_session_record(student)
    sync_student_subjects(student)


@transaction.atomic
def finalize_admission(student: Student, finalized_by=None) -> Student:
    missing_document_type_ids = get_missing_required_documents(student)
    if missing_document_type_ids:
        missing_docs = DocumentType.objects.filter(id__in=missing_document_type_ids).order_by('name')
        missing_names = ', '.join(missing_docs.values_list('name', flat=True))
        raise ValidationError(
            f"Cannot finalize admission. Pending required documents: {missing_names}."
        )

    student.admission_finalized = True
    student.admission_finalized_at = timezone.now()
    student.admission_finalized_by = finalized_by
    student.save(
        update_fields=['admission_finalized', 'admission_finalized_at', 'admission_finalized_by']
    )
    return student


@transaction.atomic
def change_student_status(student: Student, new_status: str, changed_by=None, reason: str = ''):
    allowed_statuses = {choice[0] for choice in Student.STATUS_CHOICES}
    if new_status not in allowed_statuses:
        raise ValidationError('Invalid student status.')

    old_status = student.status
    if old_status == new_status:
        return None

    student.status = new_status
    student.is_active = new_status == Student.STATUS_ACTIVE and not student.is_archived
    student.save(update_fields=['status', 'is_active'])

    StudentSessionRecord.objects.filter(
        student=student,
        session=student.session,
    ).update(status=new_status)

    return StudentStatusHistory.objects.create(
        student=student,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        reason=reason,
    )


@transaction.atomic
def archive_student(student: Student, reason: str = ''):
    student.archived_reason = reason[:255]
    student.save(update_fields=['archived_reason'])
    student.delete()


def _build_qr_fallback(payload: str):
    """
    Lightweight QR-like fallback when `qrcode` package is unavailable.
    Produces a deterministic square code based on payload hash.
    """
    import hashlib

    digest = hashlib.sha256(payload.encode('utf-8')).digest()
    size = 29
    scale = 6
    image = Image.new('RGB', (size * scale, size * scale), 'white')
    draw = ImageDraw.Draw(image)

    bit_index = 0
    for row in range(size):
        for col in range(size):
            byte = digest[(bit_index // 8) % len(digest)]
            bit = (byte >> (bit_index % 8)) & 1
            if bit:
                x1 = col * scale
                y1 = row * scale
                draw.rectangle((x1, y1, x1 + scale - 1, y1 + scale - 1), fill='black')
            bit_index += 1

    return image


def _make_qr_image(payload: str):
    try:
        import qrcode

        qr = qrcode.QRCode(border=1, box_size=8)
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(fill_color='black', back_color='white')
        return image.convert('RGB')
    except Exception:
        return _build_qr_fallback(payload)


def _build_transfer_certificate_image(student: Student):
    page = Image.new('RGB', (1240, 1754), color='white')
    draw = ImageDraw.Draw(page)

    draw.rectangle((40, 40, 1200, 1714), outline='black', width=3)
    draw.text((90, 90), student.school.name, fill='black')
    draw.text((90, 150), 'TRANSFER CERTIFICATE', fill='black')

    lines = [
        f"Student Name: {student.full_name}",
        f"Admission Number: {student.admission_number}",
        f"Date of Birth: {student.date_of_birth or '-'}",
        f"Class: {student.current_class.name if student.current_class else '-'}",
        f"Section: {student.current_section.name if student.current_section else '-'}",
        f"Session: {student.session.name}",
        f"Status: {student.get_status_display()}",
        f"Issue Date: {timezone.localdate()}",
    ]

    y = 260
    for line in lines:
        draw.text((90, y), line, fill='black')
        y += 58

    draw.text((90, 1450), 'This certificate is system generated by AHV School ERP.', fill='black')
    draw.text((900, 1580), 'Authorized Signatory', fill='black')

    if student.photo:
        try:
            with student.photo.open('rb') as photo_file:
                photo = Image.open(photo_file).convert('RGB')
                photo = ImageOps.fit(photo, (220, 260))
                page.paste(photo, (930, 250))
        except Exception:
            pass

    return page


def generate_id_card_pdf(student: Student, include_qr: bool = False) -> bytes:
    card = build_student_id_card_image(student, include_qr=include_qr)
    return image_to_pdf_bytes([card])


def generate_bulk_id_cards_pdf(students: Iterable[Student], include_qr: bool = False) -> bytes:
    cards = [build_student_id_card_image(student, include_qr=include_qr) for student in students]
    return image_to_pdf_bytes(cards)


def generate_transfer_certificate_pdf(student: Student) -> bytes:
    if student.status != Student.STATUS_TRANSFERRED:
        raise ValidationError('Transfer Certificate is available only for transferred students.')
    page = _build_transfer_certificate_image(student)
    return image_to_pdf_bytes([page])


def build_student_id_card_image(student: Student, include_qr: bool = False):
    card = Image.new('RGB', (1000, 600), color='white')
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, 1000, 90), fill=(37, 99, 235))

    school_name = student.school.name if student.school_id else 'School'
    draw.text((24, 30), school_name, fill='white')
    draw.text((24, 112), f"Name: {student.full_name}", fill='black')
    draw.text((24, 160), f"Admission No: {student.admission_number}", fill='black')
    draw.text((24, 208), f"Class: {student.current_class.name if student.current_class else '-'}", fill='black')
    draw.text((24, 256), f"Section: {student.current_section.name if student.current_section else '-'}", fill='black')
    draw.text((24, 304), f"Session: {student.session.name if student.session_id else '-'}", fill='black')

    if student.photo:
        try:
            with student.photo.open('rb') as photo_file:
                photo = Image.open(photo_file).convert('RGB')
                photo = ImageOps.fit(photo, (220, 260))
                card.paste(photo, (740, 130))
        except Exception:
            draw.rectangle((740, 130, 960, 390), outline='black')
            draw.text((790, 250), 'PHOTO', fill='black')
    else:
        draw.rectangle((740, 130, 960, 390), outline='black')
        draw.text((790, 250), 'PHOTO', fill='black')

    school_logo = getattr(student.school, 'logo', None) if student.school_id else None
    if school_logo:
        try:
            with school_logo.open('rb') as logo_file:
                logo = Image.open(logo_file).convert('RGBA')
                logo = ImageOps.contain(logo, (120, 70))
                card.paste(logo, (860, 10), mask=logo if logo.mode == 'RGBA' else None)
        except Exception:
            pass

    if include_qr:
        qr_payload = f"STUDENT:{student.id}:{student.admission_number}"
        qr_image = _make_qr_image(qr_payload)
        qr_image = ImageOps.contain(qr_image, (170, 170))
        card.paste(qr_image, (730, 420))

    return card
