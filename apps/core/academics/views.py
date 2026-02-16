from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from apps.core.users.decorators import role_required
from .models import SchoolClass, Section
from .forms import SchoolClassForm, SectionForm


@login_required
@role_required('schooladmin')
def class_list(request):
    classes = SchoolClass.objects.filter(school=request.user.school)
    return render(request, 'academics/class_list.html', {
        'classes': classes
    })


@login_required
@role_required('schooladmin')
def class_create(request):
    if request.method == 'POST':
        form = SchoolClassForm(request.POST)
        if form.is_valid():
            new_class = form.save(commit=False)
            new_class.school = request.user.school
            new_class.save()
            return redirect('class_list')
    else:
        form = SchoolClassForm()

    return render(request, 'academics/class_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def class_update(request, pk):
    school_class = get_object_or_404(
        SchoolClass,
        pk=pk,
        school=request.user.school
    )

    if request.method == 'POST':
        form = SchoolClassForm(request.POST, instance=school_class)
        if form.is_valid():
            form.save()
            return redirect('class_list')
    else:
        form = SchoolClassForm(instance=school_class)

    return render(request, 'academics/class_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def class_delete(request, pk):
    school_class = get_object_or_404(
        SchoolClass,
        pk=pk,
        school=request.user.school
    )

    school_class.delete()
    return redirect('class_list')

@login_required
@role_required('schooladmin')
def section_list(request):
    sections = Section.objects.filter(
        school_class__school=request.user.school
    )

    return render(request, 'academics/section_list.html', {
        'sections': sections
    })


@login_required
@role_required('schooladmin')
def section_create(request):
    if request.method == 'POST':
        form = SectionForm(request.POST)
        if form.is_valid():
            section = form.save(commit=False)

            # Ensure section belongs to same school
            if section.school_class.school != request.user.school:
                return redirect('section_list')

            section.save()
            return redirect('section_list')
    else:
        form = SectionForm()

    return render(request, 'academics/section_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def section_update(request, pk):
    section = get_object_or_404(
        Section,
        pk=pk,
        school_class__school=request.user.school
    )

    if request.method == 'POST':
        form = SectionForm(request.POST, instance=section)
        if form.is_valid():
            form.save()
            return redirect('section_list')
    else:
        form = SectionForm(instance=section)

    return render(request, 'academics/section_form.html', {
        'form': form
    })


@login_required
@role_required('schooladmin')
def section_delete(request, pk):
    section = get_object_or_404(
        Section,
        pk=pk,
        school_class__school=request.user.school
    )

    section.delete()
    return redirect('section_list')