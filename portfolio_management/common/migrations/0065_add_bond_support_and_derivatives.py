# Generated manually for bond amortization support and derivatives framework
# This migration adds comprehensive bond tracking capabilities including:
# - Bond-specific metadata (maturity, coupon, amortization)
# - Notional history tracking for amortizing bonds
# - Foundation for options and futures
# - New transaction types for bond redemptions

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0064_increase_price_precision"),
    ]

    operations = [
        # Add notional_change field to Transactions
        migrations.AddField(
            model_name="transactions",
            name="notional_change",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                help_text="Change in notional value (used for bond redemptions)",
                max_digits=15,
                null=True,
            ),
        ),
        # Create BondMetadata model
        migrations.CreateModel(
            name="BondMetadata",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "issue_date",
                    models.DateField(
                        blank=True, help_text="Bond issue date", null=True
                    ),
                ),
                (
                    "maturity_date",
                    models.DateField(
                        blank=True, help_text="Bond maturity date", null=True
                    ),
                ),
                (
                    "initial_notional",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Initial par/face value per bond",
                        max_digits=15,
                        null=True,
                    ),
                ),
                (
                    "coupon_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        help_text="Annual coupon rate (e.g., 5.25 for 5.25%)",
                        max_digits=8,
                        null=True,
                    ),
                ),
                (
                    "coupon_frequency",
                    models.IntegerField(
                        blank=True,
                        help_text="Number of coupon payments per year (e.g., 2 for semi-annual)",
                        null=True,
                    ),
                ),
                (
                    "is_amortizing",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this bond has amortizing principal",
                    ),
                ),
                (
                    "amortization_schedule",
                    models.JSONField(
                        blank=True,
                        help_text=(
                            "Optional: predefined amortization schedule as list of {date, amount}"
                        ),
                        null=True,
                    ),
                ),
                (
                    "bond_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("FIXED", "Fixed Rate"),
                            ("FLOATING", "Floating Rate"),
                            ("ZERO_COUPON", "Zero Coupon"),
                            ("INFLATION_LINKED", "Inflation Linked"),
                            ("CONVERTIBLE", "Convertible"),
                        ],
                        help_text="Type of bond",
                        max_length=50,
                        null=True,
                    ),
                ),
                (
                    "credit_rating",
                    models.CharField(
                        blank=True,
                        help_text="Credit rating (e.g., AAA, BB+)",
                        max_length=10,
                        null=True,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bondmetadata_metadata",
                        to="common.assets",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        # Create NotionalHistory model
        migrations.CreateModel(
            name="NotionalHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "date",
                    models.DateField(
                        db_index=True,
                        help_text="Date when the notional change occurred",
                    ),
                ),
                (
                    "notional_per_unit",
                    models.DecimalField(
                        decimal_places=6,
                        help_text="Notional/par value per unit after this change",
                        max_digits=15,
                    ),
                ),
                (
                    "change_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Amount of notional change (negative for redemptions)",
                        max_digits=15,
                        null=True,
                    ),
                ),
                (
                    "change_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("REDEMPTION", "Partial Redemption"),
                            ("MATURITY", "Maturity"),
                            ("INITIAL", "Initial Issuance"),
                            ("ADJUSTMENT", "Adjustment"),
                        ],
                        max_length=50,
                        null=True,
                    ),
                ),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notional_history",
                        to="common.assets",
                    ),
                ),
            ],
            options={
                "ordering": ["date"],
            },
        ),
        # Create OptionMetadata model
        migrations.CreateModel(
            name="OptionMetadata",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "strike_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Strike price",
                        max_digits=18,
                        null=True,
                    ),
                ),
                (
                    "expiration_date",
                    models.DateField(
                        blank=True, help_text="Option expiration date", null=True
                    ),
                ),
                (
                    "option_type",
                    models.CharField(
                        blank=True,
                        choices=[("CALL", "Call"), ("PUT", "Put")],
                        help_text="Option type",
                        max_length=10,
                        null=True,
                    ),
                ),
                (
                    "contract_size",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Number of underlying units per contract",
                        max_digits=15,
                        null=True,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="optionmetadata_metadata",
                        to="common.assets",
                    ),
                ),
                (
                    "underlying_asset",
                    models.ForeignKey(
                        blank=True,
                        help_text="Underlying asset",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="options",
                        to="common.assets",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        # Create FutureMetadata model
        migrations.CreateModel(
            name="FutureMetadata",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "expiration_date",
                    models.DateField(
                        blank=True, help_text="Futures expiration date", null=True
                    ),
                ),
                (
                    "contract_size",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Size of one futures contract",
                        max_digits=15,
                        null=True,
                    ),
                ),
                (
                    "tick_size",
                    models.DecimalField(
                        blank=True,
                        decimal_places=6,
                        help_text="Minimum price movement",
                        max_digits=15,
                        null=True,
                    ),
                ),
                (
                    "initial_margin",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Initial margin requirement",
                        max_digits=15,
                        null=True,
                    ),
                ),
                (
                    "asset",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="futuremetadata_metadata",
                        to="common.assets",
                    ),
                ),
                (
                    "underlying_asset",
                    models.ForeignKey(
                        blank=True,
                        help_text="Underlying asset",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="futures",
                        to="common.assets",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        # Add constraints
        migrations.AddConstraint(
            model_name="notionalhistory",
            constraint=models.UniqueConstraint(
                fields=("asset", "date", "change_reason"), name="unique_notional_change"
            ),
        ),
    ]
