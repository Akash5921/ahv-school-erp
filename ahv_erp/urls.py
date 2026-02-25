from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('', include('apps.core.users.urls')),
    
    path('reports/', include('apps.operations.reports.urls')),
    path('teacher/', include('apps.academics.staff.urls')),
    path('attendance/', include('apps.academics.attendance.urls')),
    path('accounts/', include('apps.finance.accounts.urls')),
    path('fees/', include('apps.finance.fees.urls')),
    path('payroll/', include('apps.finance.payroll.urls')),
    path('schools/', include('apps.core.schools.urls')),
    path('sessions/', include('apps.core.academic_sessions.urls')),
    path('students/', include('apps.academics.students.urls')),
    path('academics/', include('apps.core.academics.urls')),
    path('inventory/', include('apps.assets.inventory.urls')),
    path('transport/', include('apps.operations.transport.urls')),
    path('communication/', include('apps.operations.communication.urls')),

 

    
]
