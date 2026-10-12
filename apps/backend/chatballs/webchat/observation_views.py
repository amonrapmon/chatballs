from contextlib import contextmanager

from rest_framework.response import Response

from chatballs.i18n import t
from chatballs.webchat.access import _PublicSession, _resolved_web_session
from chatballs.webchat.api_inputs import BEARER_PREFIX
from chatballs.webchat.observations import observation_payload, record_signal, session_observations


@contextmanager
def _observation_session(request):
    # Signals use the header credential so authentication and throttling see
    # the same WebSession. Do not accept secrets in query strings or bodies.
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith(BEARER_PREFIX) or not authorization[len(BEARER_PREFIX):]:
        yield None
        return
    with _resolved_web_session(request) as (_, session):
        yield session


class WebchatObservationsView(_PublicSession):
    def post(self, request):
        with _observation_session(request) as session:
            if session is None:
                return Response({"detail": t("webchat.session_not_found")}, status=401)
            accepted, row = record_signal(session, request.data)
            return Response({"accepted": accepted, "observation": observation_payload(row)})

    def get(self, request):
        with _observation_session(request) as session:
            if session is None:
                return Response({"detail": t("webchat.session_not_found")}, status=401)
            return Response(session_observations(session))
