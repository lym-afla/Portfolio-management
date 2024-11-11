from core.positions_utils import get_positions_table_api

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.views.decorators.csrf import ensure_csrf_cookie

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ensure_csrf_cookie
def get_open_positions_table_api(request):
    return Response(get_positions_table_api(request, is_closed=False))