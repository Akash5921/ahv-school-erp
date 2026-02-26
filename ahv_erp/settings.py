"""
Django settings for ahv_erp project.

Phase 6 scope:
- Phase 0 core architecture
- Phase 1 academic master structures
- Phase 2 student lifecycle
- Phase 3 staff and HR
- Phase 4 timetable engine
- Phase 5 attendance management
- Phase 6 examination and result management
"""
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in {'1', 'true', 'yes'}
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'change-this-secret-key-in-production-1f6a6e0c97c240cb8be6ed4f0d5a2678',
)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core.users.apps.UsersConfig',
    'apps.core.schools.apps.SchoolsConfig',
    'apps.core.academic_sessions.apps.AcademicSessionsConfig',
    'apps.core.academics.apps.AcademicsConfig',
    'apps.core.students.apps.StudentsConfig',
    'apps.core.hr.apps.HrConfig',
    'apps.core.timetable.apps.TimetableConfig',
    'apps.core.attendance.apps.AttendanceConfig',
    'apps.core.exams.apps.ExamsConfig',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.schools.middleware.CurrentSchoolMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


ROOT_URLCONF = 'ahv_erp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.schools.context_processors.tenant_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'ahv_erp.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
AUTH_USER_MODEL = 'users.User'


CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'False').lower() in {'1', 'true', 'yes'}
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.getenv('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False').lower() in {'1', 'true', 'yes'}
)
SECURE_HSTS_PRELOAD = os.getenv('DJANGO_SECURE_HSTS_PRELOAD', 'False').lower() in {'1', 'true', 'yes'}
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'
LOGIN_URL = '/login/'

TEST_RUNNER = 'apps.core.test_runner.InstalledAppsOnlyDiscoverRunner'

STAFF_ATTENDANCE_EDIT_WINDOW_HOURS = int(os.getenv('STAFF_ATTENDANCE_EDIT_WINDOW_HOURS', '6'))
STUDENT_ATTENDANCE_EDIT_WINDOW_DAYS = int(os.getenv('STUDENT_ATTENDANCE_EDIT_WINDOW_DAYS', '2'))
