from django.contrib import admin

from common.models import FX, Assets, Brokers, Prices, Transactions


class BrokersAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "country",
    )  # Customize which fields to display in the list view
    search_fields = ("name",)  # Add fields for searching


class PAAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "currency",
        "exposure",
    )  # Customize which fields to display in the list view
    search_fields = ("name",)  # Add fields for searching


class PATransactionsAdmin(admin.ModelAdmin):
    list_display = (
        "security",
        "currency",
        "type",
        "date",
        "quantity",
        "price",
        "cash_flow",
        "commission",
        "comment",
    )


admin.site.register(FX)
admin.site.register(Brokers, BrokersAdmin)
admin.site.register(Assets, PAAdmin)
admin.site.register(Transactions, PATransactionsAdmin)
admin.site.register(Prices)
