# AHV School ERP - Phase 1

This repository currently implements **Phase 1** on top of the Phase 0 core foundation.

## Scope

### Phase 0 Foundation (already in place)

- Tenant lifecycle (school onboarding, tenant identity, tenant status)
- Tenant access mapping (custom domain and subdomain resolution)
- Role-based authentication and access routing
- Multi-session lifecycle (session creation, activation, one active session per school)
- Cross-cutting audit logging

### Phase 1 Academic Master Structure

- Class Master (`SchoolClass`) with session-aware design and soft-deactivation flow
- Section Master (`Section`) with class-level uniqueness and optional class teacher
- Subject Master (`Subject`) reusable across classes
- Class-Subject Mapping (`ClassSubject`) with marks rules
- Period Master (`Period`) with overlap + duration consistency checks
- Academic Configuration (`AcademicConfig`) for session-level academic rules

## Core Apps

- `apps.core.users`
- `apps.core.schools`
- `apps.core.academic_sessions`
- `apps.core.academics`

## SaaS-Ready Foundations

- `School.code` and `School.uuid` for tenant-safe identity
- `SchoolDomain` for custom-domain routing
- `CurrentSchoolMiddleware` to resolve tenant context from user or host
- Context processor exposes `current_school` and `current_session`
- Environment-driven security settings in `ahv_erp/settings.py`

## Running Locally

```bash
$env:DJANGO_DEBUG="True"
$env:DJANGO_SECRET_KEY="dev-local-secret"
python manage.py migrate
python manage.py runserver
```

### Important Environment Variables

- `DJANGO_DEBUG` (`False` by default)
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS` (comma-separated)
- `DJANGO_SECURE_SSL_REDIRECT`
- `DJANGO_SECURE_HSTS_SECONDS`

## Verification

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```
