import json
import re

from django.conf import settings
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.shortcuts import render


def detect(get_response, request):
    if any([
        # The session key is checked to avoid
        # redirect loops in development mode.
        not request.session.has_key("tz"),
        # Checks if FORBID_VPN is False or not set.
        not getattr(settings, "FORBID_VPN", False),
        # Checks if the request is an AJAX request.
        not re.search(
            r"\w+\/(?:html|xhtml\+xml|xml)",
            request.META.get("HTTP_ACCEPT"),
        ),
    ]):
        return get_response(request)

    response_attributes = ("content", "charset", "headers", "status", "reason")
    if all(map(request.session.has_key, ("tz", *response_attributes))):
        # Handles if the user's timezone differs from the
        # one determined by GeoIP API. If so, VPN is used.
        if request.POST.get("timezone", "N/A") != request.session.get("tz"):
            if hasattr(settings, "FORBIDDEN_URL"):
                return redirect(settings.FORBIDDEN_URL)
            return HttpResponseForbidden()

        # Restores the response from the session.
        response = HttpResponse(
            **{attr: request.session.get(attr) for attr in response_attributes if attr != "headers"},
            headers=json.loads(request.session.get("headers")),
        )
        # Erases the response attributes.
        for attr in response_attributes:
            request.session.pop(attr)
        return response

    # Gets the response and saves attributes in the session to restore it later.
    response = get_response(request)
    request.session["content"] = response.content.decode(response.charset)
    request.session["headers"] = json.dumps(dict(response.headers))
    request.session["charset"] = response.charset
    request.session["status"] = response.status_code
    request.session["reason"] = response.reason_phrase

    return render(request, "timezone.html", status=302)
