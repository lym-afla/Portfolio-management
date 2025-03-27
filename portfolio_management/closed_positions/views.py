import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.positions_utils import get_positions_table_api

logger = logging.getLogger(__name__)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_closed_positions_table_api(request):
    return Response(get_positions_table_api(request, is_closed=True))
