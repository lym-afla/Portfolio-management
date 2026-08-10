from datetime import date
from decimal import Decimal

import pytest

from common.models import FX


@pytest.mark.django_db
def test_fx_model_has_long_format_fields():
    """The FX model stores rates as long-format rows (from/to/rate), not named columns."""
    field_names = {f.name for f in FX._meta.get_fields()}
    assert "from_currency" in field_names
    assert "to_currency" in field_names
    assert "rate" in field_names
    assert "date" in field_names
    assert "investors" in field_names
    # NOTE: this task only ADDS the new fields. The old named columns
    # (USDEUR, USDGBP, ...) are NOT removed yet — that happens in Task 3,
    # after the data migration in Task 2. So we assert presence of the new
    # fields here, not absence of the old ones.


@pytest.mark.django_db
def test_fx_row_can_be_created_and_queried(user):
    """A long-format FX row can be created and its fields read back."""
    fx = FX.objects.create(
        date=date(2024, 6, 3),
        from_currency="RUB",
        to_currency="USD",
        rate=Decimal("90.5000"),
    )
    fx.investors.add(user)
    fetched = FX.objects.get(id=fx.id)
    assert fetched.from_currency == "RUB"
    assert fetched.to_currency == "USD"
    assert fetched.rate == Decimal("90.5000")
    assert user in fetched.investors.all()
