from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Sum
from django.db.models.functions import ExtractMonth
from apps.core.users.decorators import role_required

from apps.core.academics.models import SchoolClass, Section
from apps.academics.students.models import Student
from apps.finance.fees.models import FeePayment


@login_required
@role_required('schooladmin')
def school_admin_dashboard(request):

    school = request.user.school

    # Basic Counts
    total_students = Student.objects.for_school(school).count()
    total_classes = SchoolClass.objects.filter(school=school).count()
    total_sections = Section.objects.filter(
        school_class__school=school
    ).count()

    # Monthly Fee Collection
    monthly_data = (
        FeePayment.objects
        .filter(school=school)
        .annotate(month=ExtractMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )

    months = list(range(1, 13))
    monthly_collection = {item['month']: float(item['total']) for item in monthly_data}
    collection_list = [monthly_collection.get(m, 0) for m in months]

    context = {
        'total_students': total_students,
        'total_classes': total_classes,
        'total_sections': total_sections,
        'collection_list': collection_list,
    }

    return render(request, 'schools/school_admin_dashboard.html', context)
