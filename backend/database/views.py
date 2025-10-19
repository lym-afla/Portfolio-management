"""Database views."""

import logging
import uuid
from datetime import datetime, timezone

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
from constants import ASSET_TYPE_CHOICES, DATA_SOURCE_CHOICES
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
    """Get asset types."""
    asset_types = [{"value": value, "text": text} for value, text in ASSET_TYPE_CHOICES]
    return Response(asset_types)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_securities(request):
    """Get securities."""
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
    """Get security detail."""
    return Response(get_security_detail(request, security_id))


@api_view(["GET"])
def api_get_security_price_history(request, security_id):
    """Get security price history."""
    try:
        security = Assets.objects.get(id=security_id)
        period = request.GET.get("period", "1Y")
        # Use JWT middleware instead of session
        effective_current_date_str = getattr(
            request,
            "effective_current_date",
            datetime.now(timezone.utc).date().isoformat(),
        )
        effective_current_date = datetime.strptime(
            effective_current_date_str, "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)

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
    """Get security position history."""
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
        period = request.GET.get("period", "1Y")
        # Use JWT middleware instead of session
        effective_current_date_str = getattr(
            request,
            "effective_current_date",
            datetime.now(timezone.utc).date().isoformat(),
        )
        effective_current_date = datetime.strptime(
            effective_current_date_str, "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)

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
            f"Current position for {security.name} "
            f"as of {start_date} is {current_position}"
        )
        for transaction in transactions:
            if transaction.type == "Buy":
                current_position += transaction.quantity
            elif transaction.type == "Sell":
                current_position += transaction.quantity
            position_history.append(
                {
                    "date": transaction.date.strftime("%Y-%m-%d"),
                    "position": current_position,
                }
            )

        return JsonResponse(position_history, safe=False)
    except Assets.DoesNotExist:
        return JsonResponse({"error": "Security not found"}, status=404)


@api_view(["GET"])
def api_get_security_transactions(request, security_id):
    """Get security transactions."""
    try:
        # Use JWT middleware instead of session
        effective_current_date_str = getattr(
            request,
            "effective_current_date",
            datetime.now(timezone.utc).date().isoformat(),
        )
        effective_current_date = datetime.strptime(
            effective_current_date_str, "%Y-%m-%d"
        ).replace(tzinfo=timezone.utc)
        period = request.GET.get("period", "1Y")
        start_date = get_start_date(effective_current_date, period)

        transactions = Transactions.objects.filter(
            security__id=security_id,
            investor=request.user,
            date__lte=effective_current_date,
        ).order_by("date")

        if start_date:
            transactions = transactions.filter(date__gt=start_date)

        # Pagination
        page = int(request.GET.get("page", 1))
        items_per_page = int(request.GET.get("itemsPerPage", 10))

        paginated_transactions, pagination_data = paginate_table(
            transactions, page, items_per_page
        )
        logger.info(
            f"Paginated transactions for {security_id}: {paginated_transactions}"
        )

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
    """Get prices table."""
    return Response(get_prices_table_api(request))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_get_securities_table(request):
    """Get securities table."""
    return Response(get_securities_table_api(request))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_security_form_structure(request):
    """Get security form structure."""
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
                {"value": choice[0], "text": choice[1]}
                for choice in DATA_SOURCE_CHOICES
            ]

        # Handle specific widget types
        if isinstance(field.widget, forms.CheckboxInput):
            field_data["type"] = "checkbox"
        elif isinstance(field.widget, forms.Textarea):
            field_data["type"] = "textarea"
        elif isinstance(field.widget, forms.URLInput):
            field_data["type"] = "url"
        elif isinstance(field.widget, forms.DateInput):
            field_data["type"] = "dateinput"
        elif isinstance(field.widget, forms.NumberInput):
            field_data["type"] = "numberinput"

        structure["fields"].append(field_data)

    return Response(structure)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_security(request):
    """Create security."""
    form = SecurityForm(request.data)
    if form.is_valid():
        security = form.save(commit=False)
        # First save the security to get an ID
        security.save()

        # Now add the many-to-many relationships
        security.investors.add(request.user)

        # Save bond metadata if this is a bond
        form.save_bond_metadata(security)

        return Response(
            {
                "success": True,
                "message": "Security created successfully",
                "id": security.id,
                "name": security.name,
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(
        {"success": False, "errors": form.errors}, status=status.HTTP_400_BAD_REQUEST
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_security_details_for_editing(request, security_id):
    """Get security details for editing."""
    security = get_object_or_404(Assets, id=security_id, investors=request.user)

    result = {
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
        "tbank_instrument_uid": security.tbank_instrument_uid,
        "comment": security.comment,
        "ticker": security.ticker,
    }

    # Add bond metadata if this is a bond
    if security.type == "Bond":
        try:
            bond_meta = security.bondmetadata_metadata
            result.update(
                {
                    "initial_notional": (
                        str(bond_meta.initial_notional)
                        if bond_meta.initial_notional
                        else None
                    ),
                    "nominal_currency": bond_meta.nominal_currency,
                    "issue_date": (
                        bond_meta.issue_date.isoformat()
                        if bond_meta.issue_date
                        else None
                    ),
                    "maturity_date": (
                        bond_meta.maturity_date.isoformat()
                        if bond_meta.maturity_date
                        else None
                    ),
                    "coupon_rate": (
                        str(bond_meta.coupon_rate) if bond_meta.coupon_rate else None
                    ),
                    "coupon_frequency": bond_meta.coupon_frequency,
                    "is_amortizing": bond_meta.is_amortizing,
                    "bond_type": bond_meta.bond_type,
                    "credit_rating": bond_meta.credit_rating,
                }
            )
        except Exception:
            # No bond metadata exists yet
            pass

    return Response(result)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def api_update_security(request, security_id):
    """Update security."""
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
    except Assets.DoesNotExist:
        return Response(
            {"error": "Security not found"}, status=status.HTTP_404_NOT_FOUND
        )

    # Use form for validation and updating
    form = SecurityForm(request.data, instance=security)
    if form.is_valid():
        security = form.save()

        # Save bond metadata if this is a bond
        form.save_bond_metadata(security)

        logger.debug(f"Security updated. {security}")

        return Response(
            {
                "success": True,
                "message": "Security updated successfully",
                "id": security.id,
                "name": security.name,
            }
        )
    else:
        return Response(
            {"success": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def api_delete_security(request, security_id):
    """Delete security."""
    try:
        security = Assets.objects.get(id=security_id, investors=request.user)
    except Assets.DoesNotExist:
        return Response(
            {"error": "Security not found"}, status=status.HTTP_404_NOT_FOUND
        )

    security.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_add_price(request):
    """Add price."""
    serializer = PriceSerializer(data=request.data, investor=request.user)
    if serializer.is_valid():
        price = serializer.save()
        return Response(
            {"success": True, "message": "Price added successfully", "id": price.id},
            status=status.HTTP_201_CREATED,
        )
    return Response(
        {"success": False, "errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def api_delete_price(request, price_id):
    """Delete price."""
    try:
        price = Prices.objects.get(id=price_id)
    except Prices.DoesNotExist:
        return Response(
            {"message": "Price not found"}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        price.delete()
        return Response(
            {"message": "Price deleted successfully"}, status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_get_price_details(request, price_id):
    """Get price details."""
    price = get_object_or_404(Prices, id=price_id, security__investor=request.user)
    """Get price details."""
    return Response(
        {
            "id": price.id,
            "date": price.date.isoformat(),
            "security": price.security.id,
            "price": str(
                price.price
            ),  # Convert Decimal to string to preserve precision
        }
    )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def api_update_price(request, price_id):
    """Update price."""
    price = get_object_or_404(Prices, id=price_id, security__investors=request.user)
    """Update price."""
    serializer = PriceSerializer(
        instance=price, data=request.data, investor=request.user
    )
    if serializer.is_valid():
        """Update price."""
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
    """Price import view."""

    def get(self, request):
        """Get price import."""
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
    """Account view set."""

    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get queryset."""
        return Accounts.objects.filter(broker__investor=self.request.user).order_by(
            "name"
        )

    def perform_create(self, serializer):
        """Perform create."""
        serializer.save()

    def list(self, request, *args, **kwargs):
        """List accounts."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    def list_accounts(self, request, *args, **kwargs):
        """List accounts."""
        return Response(get_accounts_table_api(request))

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        """Get form structure."""
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
    """Update account performance view set."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        """List account performance."""
        serializer = AccountPerformanceSerializer(investor=request.user)
        form_data = serializer.get_form_data()
        return Response(form_data)

    @action(detail=False, methods=["post"])
    def validate(self, request):
        """Validate the input data."""
        serializer = AccountPerformanceSerializer(
            data=request.data, investor=request.user
        )
        if not serializer.is_valid():
            return Response(
                {"valid": False, "type": "validation", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"valid": True})

    @action(detail=False, methods=["post"])
    def start(self, request):
        """Start update process."""
        serializer = AccountPerformanceSerializer(
            data=request.data, investor=request.user
        )
        if not serializer.is_valid():
            return Response(
                {"valid": False, "type": "validation", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Use validated_data which includes parsed selection data
            update_data = {"user_id": request.user.id, **serializer.validated_data}

            session_id = str(uuid.uuid4())
            cache.set(
                f"account_performance_update_{session_id}", update_data, timeout=3600
            )

            return Response(
                {"session_id": session_id, "message": "Update process started"}
            )

        except Exception as e:
            return Response(
                {"valid": False, "type": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FXViewSet(viewsets.ModelViewSet):
    """FX view set."""

    serializer_class = FXSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"  # Use 'id' instead of 'date' for lookups

    def get_queryset(self):
        """Get queryset."""
        return FX.objects.filter(investors=self.request.user).order_by("-date")

    def perform_create(self, serializer):
        """Perform create."""
        instance = serializer.save()
        instance.investors.add(self.request.user)

    def get_object(self):
        """Get FX object."""
        fx_id = self.kwargs.get("id")
        try:
            return FX.objects.filter(investors=self.request.user).get(id=fx_id)
        except FX.DoesNotExist:
            raise NotFound(f"FX rate with id {fx_id} not found.")

    @action(detail=False, methods=["POST"])
    def get_rate(self, request):
        """Get FX rate."""
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
        """List FX."""
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
                | Q(CNYUSD__icontains=search)
            )

        # Convert queryset to list of dictionaries
        fx_data = list(
            queryset.values(
                "id", "date", "USDEUR", "USDGBP", "CHFGBP", "RUBUSD", "PLNUSD", "CNYUSD"
            )
        )

        # Apply sorting
        fx_data = sort_entries(fx_data, sort_by)

        # Paginate results
        paginated_fx_data, pagination_info = paginate_table(
            fx_data, page, items_per_page
        )

        # Format the data
        formatted_fx_data = format_table_data(
            paginated_fx_data, currency_target=None, number_of_digits=4
        )  # Assuming USD as base currency and 4 decimal places

        response_data = {
            "results": formatted_fx_data,
            "count": pagination_info["total_items"],
            "current_page": pagination_info["current_page"],
            "total_pages": pagination_info["total_pages"],
            "currencies": ["USDEUR", "USDGBP", "CHFGBP", "RUBUSD", "PLNUSD", "CNYUSD"],
        }

        return Response(response_data)

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        """Get form structure."""
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
                    {
                        "name": "CNYUSD",
                        "label": "CNY/USD",
                        "type": "number",
                        "required": True,
                    },
                ]
            }
        )

    @action(detail=False, methods=["GET"])
    def import_stats(self, request):
        """Get import stats."""
        user = request.user
        transaction_dates = (
            Transactions.objects.filter(investor=user).values("date").distinct()
        )
        total_dates = transaction_dates.count()

        fx_instances = FX.objects.filter(
            investors=user, date__in=transaction_dates.values("date")
        )
        missing_instances = total_dates - fx_instances.count()

        incomplete_instances = fx_instances.filter(
            Q(USDEUR__isnull=True)
            | Q(USDGBP__isnull=True)
            | Q(CHFGBP__isnull=True)
            | Q(RUBUSD__isnull=True)
            | Q(PLNUSD__isnull=True)
            | Q(CNYUSD__isnull=True)
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
        """Cancel import."""
        user = request.user
        import_id = f"fx_import_{user.id}"
        cache.delete(import_id)  # This will cause the import to stop
        return JsonResponse({"status": "Import cancelled"})


class BrokerViewSet(viewsets.ModelViewSet):
    """Broker view set."""

    serializer_class = BrokerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Get queryset."""
        queryset = Brokers.objects.filter(investor=self.request.user)

        # Add filter for brokers with active tokens if requested
        if self.request.query_params.get("with_active_tokens"):
            queryset = queryset.filter(Q(tinkoff_tokens__is_active=True)).distinct()

        return queryset.order_by("name")

    def perform_create(self, serializer):
        """Perform create."""
        serializer.save(investor=self.request.user)

    @action(detail=False, methods=["POST"])
    def list_brokers(self, request):
        """List brokers."""
        return Response(get_brokers_table_api(request))

    @action(detail=False, methods=["GET"])
    def form_structure(self, request):
        """Get form structure."""
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
