from django.contrib import admin
from .models import GradeScale, Student, StudentEnrollment, StudentMark

admin.site.register(Student)
admin.site.register(StudentEnrollment)
admin.site.register(StudentMark)
admin.site.register(GradeScale)
