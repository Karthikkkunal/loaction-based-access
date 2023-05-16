from django.conf import settings
from django.contrib.gis.geoip2 import GeoIP2
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from geoip2.errors import AddressNotFoundError

from ..config import Settings


class Rule:
    # Key in the geoip2 city object.
    # Subclasses should override this.
    key = None

    def __init__(self, code):
        # Two-letter ISO 3166-1 alpha-2 code.
        self.code = code

    def __call__(self, city):
        """Checks if the code is satisfied."""
        return self.code == city.get(self.key)


class CountryRule(Rule):
    key = "country_code"


class ContinentRule(Rule):
    key = "continent_code"


class Access:
    countries = "COUNTRIES"
    territories = "TERRITORIES"

    # Hold the instance of GeoIP2.
    geoip = GeoIP2()

    def __init__(self):
        self.rules = []

        if Settings.has(self.countries):
            for country in Settings.get(self.countries):
                self.rules.append(CountryRule(country.upper()))

        if Settings.has(self.territories):
            for territory in Settings.get(self.territories):
                self.rules.append(ContinentRule(territory.upper()))

    def accessible(self, city):
        """Checks if the IP address is in the white zone."""
        return any(map(lambda rule: rule(city), self.rules))

    def grants(self, city):
        """Checks if the IP address is permitted."""
        raise NotImplementedError


class PermitAccess(Access):
    def grants(self, city):
        """Checks if the IP address is permitted."""
        return not self.rules or self.accessible(city)


class ForbidAccess(Access):
    def grants(self, city):
        """Checks if the IP address is forbidden."""
        return not self.rules or not self.accessible(city)


class Factory:
    """Creates an instance of the Access class."""

    FORBID = ForbidAccess
    PERMIT = PermitAccess

    @classmethod
    def create_access(cls, action):
        return getattr(cls, action)()


class ForbidLocationMiddleware:
    """Checks if the user location is forbidden."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        city = dict()
        address = request.META.get("REMOTE_ADDR")
        address = request.META.get("HTTP_X_FORWARDED_FOR", address)
        ip_address = address.split(",")[0].strip()

        try:
            city = Access.geoip.city(ip_address)

            # Creates an instance of the Access class
            # and checks if the IP address is granted.
            action = Settings.get("OPTIONS.ACTION", "FORBID")
            granted = Factory.create_access(action).grants(city)
        except (AddressNotFoundError, Exception):
            # This happens when the IP address is not
            # in  the  GeoIP2 database. Usually, this
            # happens when the IP address is a local.
            granted = not any([
                Settings.has(Access.countries),
                Settings.has(Access.territories),
            ]) or getattr(settings, "DEBUG", False)
        finally:
            # Saves the timezone in the session for
            # comparing it with the timezone in the
            # POST request sent from user's browser
            # to detect if the user is using VPN.
            timezone = city.get("time_zone", "N/A")
            request.session["tz"] = timezone

        if granted:
            return self.get_response(request)

        # Redirects to the FORBIDDEN_LOC URL if set.
        if Settings.has("OPTIONS.URL.FORBIDDEN_LOC"):
            return redirect(Settings.get("OPTIONS.URL.FORBIDDEN_LOC"))

        return HttpResponseForbidden()