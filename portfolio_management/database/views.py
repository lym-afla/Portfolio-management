import logging
import uuid
from datetime import datetime

from django import forms
from django.core.cache import cache
from django.db.models import Q
from django.db.models.functions import Lower
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.models import FX, Accounts, Assets, Brokers, Prices, Transactions
from constants import ASSET_TYPE_CHOICES
from core.accounts_utils import get_accounts_table_api
from core.brokers_utils import get_brokers_table_api
from core.date_utils import get_start_date
from core.formatting_utils import format_table_data
from core.pagination_utils import paginate_table
from core.price_utils import get_prices_table_api
from core.securities_utils import get_securities_table_api, get_security_detail
from core.sorting_utils import sort_entries

from .forms import SecurityForm
from .serializers import (
    AccountPerformanceSerializer,
    AccountSerializer,
    BrokerSerializer,
    FXRateSerializer,
    FXSerializer,
    PriceImportSerializer,
    PriceSerializer,
    TransactionSerializer,
)

logger = logging.getLogger(__name__)


@api_view(["GET"])
def api_get_asset_types(request):
    asset_types = [{"value": value, "text": text} for value, text in ASSET_TYPE_CHOICES]
    return Response(asset_types)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_securities(request):
    user = request.user
    asset_types = request.GET.get("asset_types", "").split(",")
    account_id = request.GET.get("account_id", None)

    securities = Assets.objects.filter(investors=user)

    if asset_types and asset_types != [""]:
        securities = securities.filter(type__in=asset_types)

    if account_id:
        account = get_object_or_404(Accounts, id=account_id, broker__investor=user)
        securities = securities.filter(transactions__account=account).distinct()

    securities = securities.order_by(Lower("name")).values("id", "name", "type")
    return Response(list(securities))


@api_view(["GET"])
def api_get_security_detail(request, security_id):
    return Response(get_security_detail(request, security_id))


@api_view(["GET"])
def api_get_security_price_history(request, security_id):
    try:
        security = Assets.objects.get(id=security_id)
        period = request.GET.get("period", "1Y")
        effective_current_date = request.session.get(
            "effective_current_date", datetime.now().date().isoformat()
        )

        start_date = get_start_date(effective_current_date, period)

        print(f"Start date for {security.name} is {start_date}")

        prices = Prices.objects.filter(
            security=security, date__lte=effective_current_date
        ).order_by("date")

        if start_date:
            prices = prices.filter(date__gte=start_date)

        price_history = [
            {"date": price.date.strftime("%Y-%m-%d"), "price": float(price.price)}
            for price in prices
        ]
        return JsonResponse(price_history, safe=False)
    except Assets.DoesNotExist:
        return JsonResponse({"error": "Security not found"}, status=404)


@api_view(["GET"])
def api_get_security_position_history(request, security_id):
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
        period = request.GET.get("period", "1Y")
        effective_current_date = request.session.get(
            "effective_current_date", datetime.now().date().isoformat()
        )

        start_date = get_start_date(effective_current_date, period)

        transactions = Transactions.objects.filter(
            security=security,
            investor=request.user,
            date__lte=effective_current_date,
            quantity__isnull=False,
        ).order_by("date")

        if start_date:
            transactions = transactions.filter(date__gt=start_date)
            current_position = security.position(start_date, request.user)
            position_history = [{"date": start_date, "position": current_position}]
        else:
            current_position = 0
            position_history = []

        logger.info(
            f"Current position for {security.name} as of {start_date} is {current_position}"
        )
        # print(f"Current position for {security.name} as of {start_date} is {current_position}")
        for transaction in transactions:
            if transaction.type == "Buy":
                current_position += transaction.quantity
            elif transaction.type == "Sell":
                current_position += transaction.quantity
            position_history.append(
                {"date": transaction.date.strftime("%Y-%m-%d"), "position": current_position}
            )

        return JsonResponse(position_history, safe=False)
    except Assets.DoesNotExist:
        return JsonResponse({"error": "Security not found"}, status=404)


@api_view(["GET"])
def api_get_security_transactions(request, security_id):
    try:
        effective_current_date = request.session.get(
            "effective_current_date", datetime.now().date().isoformat()
        )
        period = request.GET.get("period", "1Y")
        start_date = get_start_date(effective_current_date, period)

        transactions = Transactions.objects.filter(
            security__id=security_id, investor=request.user
        ).order_by("date")

        if start_date:
            transactions = transactions.filter(date__gt=start_date)

        # Pagination
        page = int(request.GET.get("page", 1))
        items_per_page = int(request.GET.get("itemsPerPage", 10))

        paginated_transactions, pagination_data = paginate_table(transactions, page, items_per_page)
        logger.info(f"Paginated transactions for {security_id}: {paginated_transactions}")

        # Serialize the transactions
        serializer = TransactionSerializer(
            paginated_transactions, many=True, context={"digits": request.user.digits}
        )
        serialized_transactions = serializer.data

        return Response(
            {
                "transactions": serialized_transactions,
                "total_items": pagination_data["total_items"],
                "current_page": pagination_data["current_page"],
                "total_pages": pagination_data["total_pages"],
            }
        )
    except Assets.DoesNotExist:
        return Response({"error": "Security not found"}, status=404)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_get_prices_table(request):
    return Response(get_prices_table_api(request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_get_securities_table(request):
    return Response(get_securities_table_api(request))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_security_form_structure(request):
    form = SecurityForm()
    structure = {"fields": []}

    for field_name, field in form.fields.items():
        field_data = {
            "name": field_name,
            "label": field.label,
            "type": field.widget.__class__.__name__.lower(),
            "required": field.required,
            "choices": None,
            "initial": field.initial,
            "help_text": field.help_text,
        }

        if hasattr(field, "choices"):
            field_data["choices"] = [
                {"value": choice[0], "text": choice[1]} for choice in field.choices
            ]

        if field_name == "type":
            field_data["choices"] = [
                {"value": choice[0], "text": choice[0]}
                for choice in Assets._meta.get_field("type").choices
                if choice[0]
            ]

        if field_name == "data_source":
            field_data["choices"] = [{"value": "", "text": "None"}] + [
                {"value": choice[0], "text": choice[1]} for choice in Assets.DATA_SOURCE_CHOICES
            ]

        # Handle specific widget types
        if isinstance(field.widget, forms.CheckboxInput):
            field_data["type"] = "checkbox"
        elif isinstance(field.widget, forms.Textarea):
            field_data["type"] = "textarea"
        elif isinstance(field.widget, forms.URLInput):
            field_data["type"] = "url"

        structure["fields"].append(field_data)

    return Response(structure)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_security(request):
    form = SecurityForm(request.data)
    if form.is_valid():
        security = form.save(commit=False)
        # First save the security to get an ID
        security.save()

        # Now add the many-to-many relationships
        security.investors.add(request.user)

        return Response(
            {
                "success": True,
                "message": "Security created successfully",
                "id": security.id,
                "name": security.name,
            },
            status=status.HTTP_201_CREATED,
        )
    return Response({"success": False, "errors": form.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_security_details_for_editing(request, security_id):
    security = get_object_or_404(Assets, id=security_id, investors=request.user)
    return Response(
        {
            "id": security.id,
            "name": security.name,
            "ISIN": security.ISIN,
            "type": security.type,
            "currency": security.currency,
            "exposure": security.exposure,
            "restricted": security.restricted,
            "data_source": security.data_source,
            "yahoo_symbol": security.yahoo_symbol,
            "update_link": security.update_link,
            "comment": security.comment,
        }
    )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def api_update_security(request, security_id):
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
    except Assets.DoesNotExist:
        return Response({"error": "Security not found"}, status=status.HTTP_404_NOT_FOUND)

    # Update regular fields
    for key, value in request.data.items():
        setattr(security, key, value)

    # Save the security first
    security.save()

    logger.debug(f"Security updated. {security}")

    return Response(
        {
            "success": True,
            "message": "Security updated successfully",
            "id": security.id,
            "name": security.name,
        }
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def api_delete_security(request, security_id):
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
    except Assets.DoesNotExist:
        return Response({"error": "Security not found"}, status=status.HTTP_404_NOT_FOUND)

    security.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_add_price(request):
    serializer = PriceSerializer(data=request.data, investor=request.user)
    if serializer.is_valid():
        price = serializer.save()
        return Response(
            {"success": True, "message": "Price added successfully", "id": price.id},
            status=status.HTTP_201_CREATED,
        )
    return Response(
        {"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def api_delete_price(request, price_id):
    try:
        price = Prices.objects.get(id=price_id)
    except Prices.DoesNotExist:
        return Response({"message": "Price not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        price.delete()
        return Response({"message": "Price deleted successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_price_details(request, price_id):
    price = get_object_or_404(Prices, id=price_id, security__investor=request.user)
    return Response(
        {
            "id": price.id,
            "date": price.date.isoformat(),
            "security": price.security.id,
            "price": str(price.price),  # Convert Decimal to string to preserve precision
        }
    )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def api_update_price(request, price_id):
    price = get_object_or_404(Prices, id=price_id, security__investors=request.user)
    serializer = PriceSerializer(instance=price, data=request.data, investor=request.user)
    if serializer.is_valid():
        updated_price = serializer.save()
        return Response(
            {
                "id": updated_price.id,
                "date": updated_price.date.isoformat(),
                "security__name": updated_price.security.name,
                "security__type": updated_price.security.type,
                "security__currency": updated_price.security.currency,
                "price": str(updated_price.price),
            }
        )
    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class PriceImportView(APIView):
    def get(self, request):
        user = request.user
        securities = Assets.objects.filter(investors=user)
        accounts = Accounts.objects.filter(broker__investor=user)

        serializer = PriceImportSerializer()
        frequency_choices = dict(serializer.fields["frequency"].choices)

        return Response(
            {
                "securities": [{"id": s.id, "name": s.name} for s in securities],
                "accounts": [{"id": a.id, "name": a.name} for a in accounts],
                "frequency_choices": [
                    {"value": k, "text": v} for k, v in frequency_choices.items()
                ],
            }
        )


class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Accounts.objects.filter(broker__investor=self.request.user).order_by("name")

    def perform_create(self, serializer):
        serializer.save()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    def list_accounts(self, request, *args, **kwargs):
        return Response(get_accounts_table_api(request))

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        return Response(
            {
                "fields": [
                    {
                        "name": "name",
                        "label": "Name",
                        "type": "textinput",
                        "required": True,
                    },
                    {
                        "name": "broker",
                        "label": "Broker",
                        "type": "select",
                        "required": True,
                        "choices": [
                            {"value": broker.id, "text": broker.name}
                            for broker in Brokers.objects.filter(investor=request.user)
                        ],
                    },
                    {
                        "name": "restricted",
                        "label": "Restricted",
                        "type": "checkbox",
                        "required": False,
                    },
                    {
                        "name": "comment",
                        "label": "Comment",
                        "type": "textarea",
                        "required": False,
                    },
                ]
            }
        )


class UpdateAccountPerformanceViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """Get form structure and choices"""
        serializer = AccountPerformanceSerializer(investor=request.user)
        form_data = serializer.get_form_data()
        return Response(form_data)

    @action(detail=False, methods=["post"])
    def validate(self, request):
        """Validate the input data"""
        serializer = AccountPerformanceSerializer(data=request.data, investor=request.user)
        if not serializer.is_valid():
            return Response(
                {"valid": False, "type": "validation", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"valid": True})

    @action(detail=False, methods=["post"])
    def start(self, request):
        """Start the update process"""
        serializer = AccountPerformanceSerializer(data=request.data, investor=request.user)
        if not serializer.is_valid():
            return Response(
                {"valid": False, "type": "validation", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Use validated_data which includes parsed selection data
            update_data = {"user_id": request.user.id, **serializer.validated_data}

            session_id = str(uuid.uuid4())
            cache.set(f"account_performance_update_{session_id}", update_data, timeout=3600)

            return Response({"session_id": session_id, "message": "Update process started"})

        except Exception as e:
            return Response(
                {"valid": False, "type": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FXViewSet(viewsets.ModelViewSet):
    serializer_class = FXSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"  # Use 'id' instead of 'date' for lookups

    def get_queryset(self):
        return FX.objects.filter(investors=self.request.user).order_by("-date")

    def perform_create(self, serializer):
        instance = serializer.save()
        instance.investors.add(self.request.user)

    def get_object(self):
        fx_id = self.kwargs.get("id")
        try:
            return FX.objects.filter(investors=self.request.user).get(id=fx_id)
        except FX.DoesNotExist:
            raise NotFound(f"FX rate with id {fx_id} not found.")

    @action(detail=False, methods=["POST"])
    def get_rate(self, request):
        serializer = FXRateSerializer(data=request.data)
        if serializer.is_valid():
            source = serializer.validated_data["source"]
            target = serializer.validated_data["target"]
            date = serializer.validated_data["date"]

            try:
                rate = FX.get_rate(source, target, date, self.request.user)
                return Response(rate)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["POST"])
    def list_fx(self, request):
        # Extract parameters from request data
        start_date = request.data.get("startDate")
        end_date = request.data.get("endDate")
        page = int(request.data.get("page", 1))
        items_per_page = int(request.data.get("itemsPerPage", 10))
        sort_by = request.data.get("sortBy")
        search = request.data.get("search", "")

        # Filter queryset
        queryset = self.get_queryset()
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        # Apply search
        if search:
            queryset = queryset.filter(
                Q(date__icontains=search)
                | Q(USDEUR__icontains=search)
                | Q(USDGBP__icontains=search)
                | Q(CHFGBP__icontains=search)
                | Q(RUBUSD__icontains=search)
                | Q(PLNUSD__icontains=search)
            )

        # Convert queryset to list of dictionaries
        fx_data = list(
            queryset.values("id", "date", "USDEUR", "USDGBP", "CHFGBP", "RUBUSD", "PLNUSD")
        )

        # Apply sorting
        fx_data = sort_entries(fx_data, sort_by)

        # Paginate results
        paginated_fx_data, pagination_info = paginate_table(fx_data, page, items_per_page)

        # Format the data
        formatted_fx_data = format_table_data(
            paginated_fx_data, currency_target=None, number_of_digits=4
        )  # Assuming USD as base currency and 4 decimal places

        response_data = {
            "results": formatted_fx_data,
            "count": pagination_info["total_items"],
            "current_page": pagination_info["current_page"],
            "total_pages": pagination_info["total_pages"],
            "currencies": ["USDEUR", "USDGBP", "CHFGBP", "RUBUSD", "PLNUSD"],
        }

        return Response(response_data)

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        return Response(
            {
                "fields": [
                    {
                        "name": "date",
                        "label": "Date",
                        "type": "datepicker",
                        "required": True,
                    },
                    {
                        "name": "USDEUR",
                        "label": "USD/EUR",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "name": "USDGBP",
                        "label": "USD/GBP",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "name": "CHFGBP",
                        "label": "CHF/GBP",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "name": "RUBUSD",
                        "label": "RUB/USD",
                        "type": "number",
                        "required": True,
                    },
                    {
                        "name": "PLNUSD",
                        "label": "PLN/USD",
                        "type": "number",
                        "required": True,
                    },
                ]
            }
        )

    @action(detail=False, methods=["GET"])
    def import_stats(self, request):
        user = request.user
        transaction_dates = Transactions.objects.filter(investor=user).values("date").distinct()
        total_dates = transaction_dates.count()

        fx_instances = FX.objects.filter(investors=user, date__in=transaction_dates.values("date"))
        missing_instances = total_dates - fx_instances.count()

        incomplete_instances = fx_instances.filter(
            Q(USDEUR__isnull=True)
            | Q(USDGBP__isnull=True)
            | Q(CHFGBP__isnull=True)
            | Q(RUBUSD__isnull=True)
            | Q(PLNUSD__isnull=True)
        ).count()

        stats = {
            "total_dates": total_dates,
            "missing_instances": missing_instances,
            "incomplete_instances": incomplete_instances,
        }
        logger.info(f"FX import stats for user {user.id}: {stats}")
        return Response(stats)

    @action(detail=False, methods=["POST"])
    def cancel_import(self, request):
        user = request.user
        import_id = f"fx_import_{user.id}"
        cache.delete(import_id)  # This will cause the import to stop
        return JsonResponse({"status": "Import cancelled"})


class BrokerViewSet(viewsets.ModelViewSet):
    serializer_class = BrokerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Brokers.objects.filter(investor=self.request.user)

        # Add filter for brokers with active tokens if requested
        if self.request.query_params.get("with_active_tokens"):
            queryset = queryset.filter(Q(tinkoff_tokens__is_active=True)).distinct()

        return queryset.order_by("name")

    def perform_create(self, serializer):
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=["POST"])
    def list_brokers(self, request):
        return Response(get_brokers_table_api(request))

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        return Response(
            {
                "fields": [
                    {
                        "name": "name",
                        "label": "Name",
                        "type": "textinput",
                        "required": True,
                    },
                    {
                        "name": "country",
                        "label": "Country",
                        "type": "textinput",
                        "required": True,
                    },
                    {
                        "name": "comment",
                        "label": "Comment",
                        "type": "textarea",
                        "required": False,
                    },
                ]
            }
        )
