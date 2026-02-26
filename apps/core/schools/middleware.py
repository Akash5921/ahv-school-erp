from apps.core.schools.services import resolve_school_by_host


class CurrentSchoolMiddleware:
    """
    Resolves tenant context for every request.
    Priority:
    1) authenticated user school
    2) host/domain mapping
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.current_school = None
        request.current_session = None

        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'school_id', None):
            request.current_school = user.school
        else:
            request.current_school = resolve_school_by_host(request.get_host())

        if request.current_school:
            request.current_session = request.current_school.current_session

        return self.get_response(request)
