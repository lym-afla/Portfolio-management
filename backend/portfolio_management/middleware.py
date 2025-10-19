"""Initialize effective current date middleware."""

from datetime import date

import structlog

logger = structlog.get_logger(__name__)


class InitializeEffectiveDateMiddleware:
    """Initialize effective current date middleware."""

    def __init__(self, get_response):
        """Initialize effective current date middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Initialize effective current date middleware."""
        # Log session state before processing
        session_key = getattr(request.session, "_session_key", "no-key")
        session_id = request.session.session_key

        # Log session cookies for debugging
        cookies = {}
        for name, value in request.COOKIES.items():
            if "session" in name.lower() or "csrftoken" in name.lower():
                cookies[name] = (
                    value[:10] + "..." if value and len(value) > 10 else value
                )

        logger.info(
            "Middleware start",
            path=request.path,
            method=request.method,
            session_id=session_id,
            session_key=(
                session_key[:20] + "..."
                if session_key and len(session_key) > 20
                else session_key
            ),
            session_cookies=cookies,
            session_data=dict(request.session.items()),
            has_effective_date="effective_current_date" in request.session,
            effective_date=request.session.get("effective_current_date", "not-set"),
        )

        # Check if effective_current_date exists in session
        has_effective_date = "effective_current_date" in request.session
        logger.info(
            "Middleware checking session",
            has_effective_date=has_effective_date,
            session_keys=list(request.session.keys()),
            effective_current_date=request.session.get(
                "effective_current_date", "NOT_FOUND"
            ),
        )

        if not has_effective_date:
            default_date = date.today().isoformat()
            request.session["effective_current_date"] = default_date
            request.session.modified = True
            logger.warning(
                "Middleware set default date - NO EFFECTIVE DATE FOUND IN SESSION",
                default_date=default_date,
                session_modified=request.session.modified,
                session_data=dict(request.session.items()),
            )
        else:
            logger.info(
                "Middleware using existing date",
                effective_date=request.session["effective_current_date"],
            )

        response = self.get_response(request)

        # Log response cookies for debugging
        response_cookies = {}
        if hasattr(response, "cookies"):
            for name, value in response.cookies.items():
                if "session" in name.lower() or "csrftoken" in name.lower():
                    response_cookies[name] = (
                        str(value)[:50] + "..."
                        if str(value) and len(str(value)) > 50
                        else str(value)
                    )

        # Enhanced debugging for session cookie issues
        all_response_cookies = {}
        if hasattr(response, "cookies"):
            for name, value in response.cookies.items():
                all_response_cookies[name] = (
                    str(value)[:50] + "..."
                    if str(value) and len(str(value)) > 50
                    else str(value)
                )

        # Check Django's session cookie settings
        from django.conf import settings

        session_settings = {
            "SESSION_ENGINE": settings.SESSION_ENGINE,
            "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,
            "SESSION_COOKIE_HTTPONLY": settings.SESSION_COOKIE_HTTPONLY,
            "SESSION_COOKIE_SAMESITE": settings.SESSION_COOKIE_SAMESITE,
            "SESSION_COOKIE_AGE": settings.SESSION_COOKIE_AGE,
            "CORS_ALLOW_CREDENTIALS": getattr(
                settings, "CORS_ALLOW_CREDENTIALS", False
            ),
            "CORS_ALLOWED_ORIGINS": getattr(settings, "CORS_ALLOWED_ORIGINS", []),
        }

        # Log session state after processing
        logger.info(
            "Middleware end",
            path=request.path,
            session_data=dict(request.session.items()),
            effective_date=request.session.get("effective_current_date", "not-set"),
            session_modified=request.session.modified,
            response_status=response.status_code,
            response_cookies=response_cookies,
            all_response_cookies=all_response_cookies,
            set_cookie_header=(
                response.get("Set-Cookie") if "Set-Cookie" in response else None
            ),
            session_settings=session_settings,
        )

        # Ensure session is saved
        if request.session.modified:
            request.session.save()
            logger.info("Middleware saved session")

        return response
