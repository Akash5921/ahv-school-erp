def tenant_context(request):
    return {
        'current_school': getattr(request, 'current_school', None),
        'current_session': getattr(request, 'current_session', None),
        'erp_phase': 'Phase 6',
    }
