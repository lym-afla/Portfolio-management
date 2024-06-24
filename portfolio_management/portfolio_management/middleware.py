# myapp/middleware.py
from datetime import date

class InitializeEffectiveDateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Initialize effective_current_date if not set
        if 'effective_current_date' not in request.session:
            request.session['effective_current_date'] = date.today().strftime('%Y-%m-%d')
        response = self.get_response(request)
        return response
