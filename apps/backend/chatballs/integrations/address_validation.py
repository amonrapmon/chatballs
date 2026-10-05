from django.core.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.integrations.external_server import validate_http_address


class HttpAddressValidationView(APIView):
    permission_classes = [HasCapability]
    required_capabilities = {"POST": "integrations.manage"}

    def post(self, request: Request) -> Response:
        try:
            validate_http_address(str(request.data.get("url") or "").strip())
        except ValidationError as error:
            return Response({"errors": error.message_dict})
        return Response({"errors": {}})
