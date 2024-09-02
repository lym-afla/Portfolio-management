# myapp/middleware.py
from datetime import date

class InitializeEffectiveDateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'effective_current_date' not in request.session:
            request.session['effective_current_date'] = date.today().isoformat()
            request.session.modified = True
        response = self.get_response(request)
        return response