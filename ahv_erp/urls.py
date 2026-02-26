from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('', include('apps.core.users.urls')),
    path('schools/', include('apps.core.schools.urls')),
    path('sessions/', include('apps.core.academic_sessions.urls')),
    path('academics/', include('apps.core.academics.urls')),
    path('students/', include('apps.core.students.urls')),
    path('hr/', include('apps.core.hr.urls')),
    path('timetable/', include('apps.core.timetable.urls')),
    path('attendance/', include('apps.core.attendance.urls')),
    path('exams/', include('apps.core.exams.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
