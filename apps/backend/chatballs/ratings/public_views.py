from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from chatballs.ratings.credentials import bearer_credential, hash_credential
from chatballs.ratings.public_service import (
    question_payload,
    resolved_request,
    result_payload,
    submit_rating,
)


class RatingIPThrottle(SimpleRateThrottle):
    scope = "rating_ip"
    rate = "60/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class RatingCredentialThrottle(SimpleRateThrottle):
    scope = "rating_credential"
    rate = "10/min"

    def get_cache_key(self, request, view):
        token = bearer_credential(request)
        return self.cache_format % {"scope": self.scope, "ident": hash_credential(token)} if token else None


class PublicRatingView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RatingIPThrottle, RatingCredentialThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def get(self, request):
        with resolved_request(bearer_credential(request)) as (target, _context):
            return Response(question_payload(target))

    def post(self, request):
        with resolved_request(bearer_credential(request)) as (target, context):
            result, created = submit_rating(target, context, request.data)
            return Response(result_payload(result), status=201 if created else 200)
