import json
import re
from datetime import datetime

from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.timezone import utc

from ..config import Settings


class ForbidNetworkMiddleware:
    """Checks if the user network is forbidden."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response_attributes = ("content", "charset", "status", "reason")

        def erase_response_attributes():
            for attr in response_attributes:
                request.session.pop(attr)

        if any([
            # Checks if VPN is False or not set.
            not Settings.get("OPTIONS.VPN", False),
            # Checks if the request is an AJAX request.
            not re.search(
                r"\w+\/(?:html|xhtml\+xml|xml)",
                request.META.get("HTTP_ACCEPT"),
            ),
        ]):
            return self.get_response(request)

        access = datetime.utcnow().replace(tzinfo=utc).timestamp()

        # Checks if access is not timed out yet.
        if Settings.has("OPTIONS.PERIOD") and request.session.has_key("ACCESS") and \
                access - request.session.get("ACCESS") < Settings.get("OPTIONS.PERIOD"):
            return self.get_response(request)

        if all(map(request.session.has_key, ("tz", *response_attributes))):
            # Handles if the user's timezone differs from the
            # one determined by GeoIP API. If so, VPN is used.
            if request.session.get("tz") != "N/A" and \
                    request.POST.get("timezone", "N/A") != request.session.get("tz"):
                erase_response_attributes()
                # Redirects to the FORBIDDEN_VPN URL if set.
                if Settings.has("OPTIONS.URL.FORBIDDEN_VPN"):
                    return redirect(Settings.get("OPTIONS.URL.FORBIDDEN_VPN"))
                return HttpResponseForbidden()

            # Restores the response from the session.
            response = HttpResponse(**{
                attr: request.session.get(attr) for attr in response_attributes
            })
            if hasattr(response, "headers"):
                response.headers = json.loads(request.session.get("headers"))
            request.session["ACCESS"] = access
            erase_response_attributes()
            return response

        # Gets the response and saves attributes in the session to restore it later.
        response = self.get_response(request)
        if hasattr(response, "headers"):
            # In older versions of Django, HttpResponse does not have headers.
            request.session["headers"] = json.dumps(dict(response.headers))
        request.session["content"] = response.content.decode(response.charset)
        request.session["charset"] = response.charset
        request.session["status"] = response.status_code
        request.session["reason"] = response.reason_phrase

        return render(request, "timezone.html", status=302)