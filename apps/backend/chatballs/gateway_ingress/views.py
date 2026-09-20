from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .delivery_status import accept_gateway_delivery_status
from .security import GatewayIngressError
from .services import accept_gateway_inbound


class GatewayInboundView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request: Request, integration_id: int) -> Response:
        try:
            accept_gateway_inbound(
                integration_id=integration_id,
                authorization=request.headers.get("Authorization", ""),
                payload=request.data,
            )
        except GatewayIngressError as error:
            return Response({"detail": error.detail}, status=error.status)
        return Response({"accepted": True}, status=202)


class GatewayDeliveryStatusView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request: Request, integration_id: int) -> Response:
        try:
            accept_gateway_delivery_status(
                integration_id=integration_id,
                authorization=request.headers.get("Authorization", ""),
                payload=request.data,
            )
        except GatewayIngressError as error:
            return Response({"detail": error.detail}, status=error.status)
        return Response({"accepted": True}, status=202)
