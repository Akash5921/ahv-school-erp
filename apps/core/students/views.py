from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section
from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import (
    DocumentTypeForm,
    ParentForm,
    StudentDocumentForm,
    StudentForm,
    StudentStatusForm,
)
from .models import DocumentType, Parent, Student, StudentDocument
from .services import (
    archive_student,
    change_student_status,
    finalize_admission,
    generate_bulk_id_cards_pdf,
    generate_id_card_pdf,
    generate_transfer_certificate_pdf,
    get_missing_required_documents,
    get_required_document_types,
    sync_student_academic_links,
)


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


def _resolve_selected_session(request, school):
    sessions = _school_sessions(school)
    session_id = request.GET.get('session') or request.POST.get('filter_session')

    selected_session = None
    if session_id:
        selected_session = sessions.filter(id=session_id).first()
    elif school.current_session_id:
        selected_session = sessions.filter(id=school.current_session_id).first()

    return sessions, selected_session


def _truthy_param(value):
    return str(value).lower() in {'1', 'true', 'yes', 'on'}


def _get_filtered_students_queryset(request, school):
    sessions, selected_session = _resolve_selected_session(request, school)

    class_id = request.GET.get('class')
    section_id = request.GET.get('section')
    status = request.GET.get('status')
    search = (request.GET.get('q') or '').strip()

    students = Student.objects.filter(
        school=school,
        is_archived=False,
    ).select_related(
        'session',
        'current_class',
        'current_section',
    )

    if selected_session:
        students = students.filter(session=selected_session)
    if class_id:
        students = students.filter(current_class_id=class_id)
    if section_id:
        students = students.filter(current_section_id=section_id)
    if status:
        students = students.filter(status=status)
    if search:
        students = students.filter(
            Q(admission_number__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    classes = SchoolClass.objects.filter(school=school)
    if selected_session:
        classes = classes.filter(session=selected_session)
    classes = classes.order_by('display_order', 'name')

    sections = Section.objects.filter(school_class__school=school)
    if class_id:
        sections = sections.filter(school_class_id=class_id)
    else:
        sections = sections.none()
    sections = sections.order_by('school_class__name', 'name')

    return {
        'students': students.order_by('admission_number', 'id'),
        'sessions': sessions,
        'selected_session': selected_session,
        'classes': classes,
        'sections': sections,
        'selected_class_id': int(class_id) if str(class_id).isdigit() else None,
        'selected_section_id': int(section_id) if str(section_id).isdigit() else None,
        'selected_status': status,
        'search_query': search,
    }


@login_required
@role_required('schooladmin')
def student_list(request):
    context = _get_filtered_students_queryset(request, request.user.school)
    return render(request, 'students_core/student_list.html', context)


@login_required
@role_required('schooladmin')
def student_create(request):
    school = request.user.school
    _, selected_session = _resolve_selected_session(request, school)

    if request.method == 'POST':
        student_form = StudentForm(
            request.POST,
            request.FILES,
            school=school,
            session=selected_session,
        )
        parent_form = ParentForm(request.POST, prefix='parent')

        if student_form.is_valid() and parent_form.is_valid():
            with transaction.atomic():
                student = student_form.save(commit=False)
                student.school = school
                student.save()

                if parent_form.has_data():
                    parent_data = parent_form.cleaned_data.copy()
                    Parent.objects.update_or_create(
                        student=student,
                        defaults=parent_data,
                    )

                sync_student_academic_links(student)

            log_audit_event(
                request=request,
                action='students.student_created',
                school=school,
                target=student,
                details=f"Admission={student.admission_number}, Session={student.session_id}",
            )
            messages.success(request, 'Student admission created successfully.')
            return redirect('student_list')
    else:
        student_form = StudentForm(school=school, session=selected_session)
        parent_form = ParentForm(prefix='parent')

    return render(request, 'students_core/student_form.html', {
        'student_form': student_form,
        'parent_form': parent_form,
        'selected_session': selected_session,
    })


@login_required
@role_required('schooladmin')
def student_update(request, pk):
    school = request.user.school
    student = get_object_or_404(Student, pk=pk, school=school)
    existing_parent = getattr(student, 'parent_info', None)

    if request.method == 'POST':
        student_form = StudentForm(request.POST, request.FILES, instance=student, school=school)
        parent_form = ParentForm(request.POST, instance=existing_parent, prefix='parent')

        if student_form.is_valid() and parent_form.is_valid():
            with transaction.atomic():
                student = student_form.save()

                if parent_form.has_data():
                    parent = parent_form.save(commit=False)
                    parent.student = student
                    parent.save()
                elif existing_parent:
                    existing_parent.delete()

                sync_student_academic_links(student)

            log_audit_event(
                request=request,
                action='students.student_updated',
                school=school,
                target=student,
                details=f"Admission={student.admission_number}",
            )
            messages.success(request, 'Student profile updated successfully.')
            return redirect('student_list')
    else:
        student_form = StudentForm(instance=student, school=school)
        parent_form = ParentForm(instance=existing_parent, prefix='parent')

    return render(request, 'students_core/student_form.html', {
        'student_form': student_form,
        'parent_form': parent_form,
        'student': student,
    })


@login_required
@role_required('schooladmin')
@require_POST
def student_archive(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)
    reason = (request.POST.get('reason') or '').strip()

    archive_student(student, reason=reason)

    log_audit_event(
        request=request,
        action='students.student_archived',
        school=request.user.school,
        target=student,
        details=f"Reason={reason or '-'}",
    )
    messages.success(request, 'Student archived successfully.')
    return redirect('student_list')


@login_required
@role_required('schooladmin')
def student_parent_update(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)
    existing_parent = getattr(student, 'parent_info', None)

    if request.method == 'POST':
        form = ParentForm(request.POST, instance=existing_parent)
        if form.is_valid():
            if form.has_data():
                parent = form.save(commit=False)
                parent.student = student
                parent.save()
                message = 'Parent information saved successfully.'
            else:
                if existing_parent:
                    existing_parent.delete()
                message = 'Parent information cleared successfully.'

            log_audit_event(
                request=request,
                action='students.parent_updated',
                school=request.user.school,
                target=student,
                details=f"Admission={student.admission_number}",
            )
            messages.success(request, message)
            return redirect('student_list')
    else:
        form = ParentForm(instance=existing_parent)

    return render(request, 'students_core/parent_form.html', {
        'form': form,
        'student': student,
    })


@login_required
@role_required('schooladmin')
def student_status_update(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)

    if request.method == 'POST':
        form = StudentStatusForm(request.POST)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            reason = form.cleaned_data['reason']
            history = change_student_status(
                student=student,
                new_status=new_status,
                changed_by=request.user,
                reason=reason,
            )

            if history:
                log_audit_event(
                    request=request,
                    action='students.status_changed',
                    school=request.user.school,
                    target=student,
                    details=f"{history.old_status} -> {history.new_status}; Reason={reason or '-'}",
                )
                messages.success(request, 'Student status updated successfully.')
            else:
                messages.info(request, 'Student status was unchanged.')
            return redirect('student_list')
    else:
        form = StudentStatusForm(initial={'status': student.status})

    return render(request, 'students_core/status_form.html', {
        'form': form,
        'student': student,
    })


@login_required
@role_required('schooladmin')
def document_type_list(request):
    document_types = DocumentType.objects.filter(school=request.user.school).order_by('name')
    return render(request, 'students_core/document_type_list.html', {
        'document_types': document_types,
    })


@login_required
@role_required('schooladmin')
def document_type_create(request):
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST)
        if form.is_valid():
            document_type = form.save(commit=False)
            document_type.school = request.user.school
            document_type.save()
            log_audit_event(
                request=request,
                action='students.document_type_created',
                school=request.user.school,
                target=document_type,
                details=f"Name={document_type.name}",
            )
            messages.success(request, 'Document type created successfully.')
            return redirect('document_type_list')
    else:
        form = DocumentTypeForm()

    return render(request, 'students_core/document_type_form.html', {'form': form})


@login_required
@role_required('schooladmin')
def document_type_update(request, pk):
    document_type = get_object_or_404(DocumentType, pk=pk, school=request.user.school)

    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, instance=document_type)
        if form.is_valid():
            document_type = form.save()
            log_audit_event(
                request=request,
                action='students.document_type_updated',
                school=request.user.school,
                target=document_type,
                details=f"Name={document_type.name}",
            )
            messages.success(request, 'Document type updated successfully.')
            return redirect('document_type_list')
    else:
        form = DocumentTypeForm(instance=document_type)

    return render(request, 'students_core/document_type_form.html', {
        'form': form,
        'document_type': document_type,
    })


@login_required
@role_required('schooladmin')
@require_POST
def document_type_deactivate(request, pk):
    document_type = get_object_or_404(DocumentType, pk=pk, school=request.user.school)
    document_type.is_active = False
    document_type.save(update_fields=['is_active'])

    log_audit_event(
        request=request,
        action='students.document_type_deactivated',
        school=request.user.school,
        target=document_type,
        details=f"Name={document_type.name}",
    )
    messages.success(request, 'Document type deactivated successfully.')
    return redirect('document_type_list')


@login_required
@role_required('schooladmin')
def student_document_list(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)

    if request.method == 'POST':
        form = StudentDocumentForm(request.POST, request.FILES, student=student)
        if form.is_valid():
            student_document = form.save(commit=False)
            student_document.student = student
            student_document.status = StudentDocument.STATUS_PENDING
            student_document.save()

            log_audit_event(
                request=request,
                action='students.document_uploaded',
                school=request.user.school,
                target=student_document,
                details=f"Student={student.admission_number}",
            )
            messages.success(request, 'Document uploaded successfully.')
            return redirect('student_document_list', pk=student.pk)
    else:
        form = StudentDocumentForm(student=student)

    documents = student.documents.select_related('document_type', 'verified_by').order_by('document_type__name')
    required_types = get_required_document_types(student)
    missing_required_ids = set(get_missing_required_documents(student))

    return render(request, 'students_core/student_document_list.html', {
        'student': student,
        'documents': documents,
        'form': form,
        'required_types': required_types,
        'missing_required_ids': missing_required_ids,
    })


@login_required
@role_required('schooladmin')
@require_POST
def student_document_verify(request, student_pk, document_pk):
    student = get_object_or_404(Student, pk=student_pk, school=request.user.school)
    document = get_object_or_404(StudentDocument, pk=document_pk, student=student)

    new_status = request.POST.get('status')
    remarks = (request.POST.get('remarks') or '').strip()

    if new_status not in {choice[0] for choice in StudentDocument.STATUS_CHOICES}:
        messages.error(request, 'Invalid document status provided.')
        return redirect('student_document_list', pk=student.pk)

    document.status = new_status
    document.remarks = remarks
    if new_status in {StudentDocument.STATUS_APPROVED, StudentDocument.STATUS_REJECTED}:
        document.verified_by = request.user
        document.verified_at = timezone.now()
    else:
        document.verified_by = None
        document.verified_at = None

    document.save(update_fields=['status', 'remarks', 'verified_by', 'verified_at'])

    log_audit_event(
        request=request,
        action='students.document_verified',
        school=request.user.school,
        target=document,
        details=f"Status={new_status}",
    )
    messages.success(request, 'Document verification status updated.')
    return redirect('student_document_list', pk=student.pk)


@login_required
@role_required('schooladmin')
@require_POST
def student_finalize_admission(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)

    try:
        finalize_admission(student=student, finalized_by=request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        log_audit_event(
            request=request,
            action='students.admission_finalized',
            school=request.user.school,
            target=student,
            details=f"Admission={student.admission_number}",
        )
        messages.success(request, 'Admission finalized successfully.')

    return redirect('student_document_list', pk=student.pk)


@login_required
@role_required('schooladmin')
def student_id_card_download(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)
    include_qr = _truthy_param(request.GET.get('qr'))

    pdf_bytes = generate_id_card_pdf(student, include_qr=include_qr)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="id_card_{student.admission_number}.pdf"'
    return response


@login_required
@role_required('schooladmin')
def student_id_card_bulk_download(request):
    school = request.user.school
    context = _get_filtered_students_queryset(request, school)
    students = context['students']

    if not students.exists():
        messages.error(request, 'No students found for selected filters.')
        query = request.GET.urlencode()
        if query:
            return redirect(f"{reverse('student_list')}?{query}")
        return redirect('student_list')

    include_qr = _truthy_param(request.GET.get('qr'))
    pdf_bytes = generate_bulk_id_cards_pdf(students, include_qr=include_qr)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"id_cards_{school.code or school.id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@role_required('schooladmin')
def student_transfer_certificate_download(request, pk):
    student = get_object_or_404(Student, pk=pk, school=request.user.school)

    try:
        pdf_bytes = generate_transfer_certificate_pdf(student)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('student_status_update', pk=student.pk)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="transfer_certificate_{student.admission_number}.pdf"'
    )
    return response
