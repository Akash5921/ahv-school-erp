from apps.core.schools.models import School, SchoolDomain


def normalize_host(host):
    if not host:
        return ''
    normalized = host.strip().lower().split(':', 1)[0]
    if normalized.startswith('www.'):
        normalized = normalized[4:]
    return normalized


def resolve_school_by_host(host):
    normalized = normalize_host(host)
    if not normalized:
        return None

    domain_match = (
        SchoolDomain.objects.select_related('school')
        .filter(
            domain=normalized,
            is_active=True,
            school__is_active=True,
        )
        .first()
    )
    if domain_match:
        return domain_match.school

    # Subdomain fallback, e.g. tenant.example.com or tenant.localhost
    parts = normalized.split('.')
    if len(parts) >= 3:
        subdomain = parts[0]
    elif len(parts) == 2 and parts[1] == 'localhost':
        subdomain = parts[0]
    else:
        subdomain = ''

    if not subdomain:
        return None

    return School.objects.filter(
        subdomain=subdomain,
        is_active=True,
    ).first()
