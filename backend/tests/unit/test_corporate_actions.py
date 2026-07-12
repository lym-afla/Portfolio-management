"""Tests for services/corporate_actions.py — execute_merger and execute_transfer.

Covers validation error paths, all-stock merger execution, all-cash merger
execution, and asset transfer execution. These exercise the inlined workflow
logic that was extracted from the viewset in Phase 1 Task 11.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from common.models import Accounts, Assets, Brokers, Transactions
from services.corporate_actions import CorporateActionError, execute_merger, execute_transfer

CustomUser = get_user_model()


@pytest.fixture
def investor(db):
    return CustomUser.objects.create_user(username="corptest", password="pw")


@pytest.fixture
def broker(investor):
    return Brokers.objects.create(name="TestBroker", investor=investor)


@pytest.fixture
def account(broker, investor):
    return Accounts.objects.create(
        name="TestAcct", broker=broker, native_id="CA1", is_active=True
    )


@pytest.fixture
def old_security(investor):
    s = Assets.objects.create(
        name="Old Co", ISIN="US0000000001", type="Stock", currency="USD", exposure="Equity"
    )
    s.investors.add(investor)
    return s


@pytest.fixture
def new_security(investor):
    s = Assets.objects.create(
        name="New Co", ISIN="US0000000002", type="Stock", currency="USD", exposure="Equity"
    )
    s.investors.add(investor)
    return s


@pytest.fixture
def second_account(broker, investor):
    return Accounts.objects.create(
        name="SecondAcct", broker=broker, native_id="CA2", is_active=True
    )


# =============================================================================
# execute_merger — validation errors (covers lines 124-156)
# =============================================================================


@pytest.mark.django_db
def test_execute_merger_missing_old_security_id(investor):
    """Missing old_security_id raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="old_security_id and merger_date are required"):
        execute_merger(investor, None, None, None, None, None)


@pytest.mark.django_db
def test_execute_merger_missing_merger_date(investor, old_security):
    """Missing merger_date raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="old_security_id and merger_date are required"):
        execute_merger(investor, old_security.id, None, None, None, None)


@pytest.mark.django_db
def test_execute_merger_invalid_date_format(investor, old_security):
    """Invalid date format raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="Invalid merger_date format"):
        execute_merger(investor, old_security.id, None, "15-Jan-2024", None, None)


@pytest.mark.django_db
def test_execute_merger_conversion_ratio_required_with_new_security(investor, old_security, new_security):
    """Providing new_security_id without conversion_ratio raises error."""
    with pytest.raises(CorporateActionError, match="conversion_ratio is required"):
        execute_merger(
            investor, old_security.id, new_security.id, "2024-01-15",
            conversion_ratio=None, cash_per_share="0",
        )


@pytest.mark.django_db
def test_execute_merger_invalid_conversion_ratio(investor, old_security, new_security):
    """Non-numeric conversion_ratio raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="Invalid conversion_ratio"):
        execute_merger(
            investor, old_security.id, new_security.id, "2024-01-15",
            conversion_ratio="abc", cash_per_share="0",
        )


@pytest.mark.django_db
def test_execute_merger_invalid_cash_per_share(investor, old_security):
    """Non-numeric cash_per_share raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="Invalid cash_per_share"):
        execute_merger(
            investor, old_security.id, None, "2024-01-15",
            conversion_ratio=None, cash_per_share="xyz",
        )


@pytest.mark.django_db
def test_execute_merger_no_position(investor, old_security):
    """Old security with no position raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="no positive position"):
        execute_merger(investor, old_security.id, None, "2024-01-15", None, None)


# =============================================================================
# execute_merger — all-stock merger execution
# =============================================================================


@pytest.mark.django_db
def test_execute_merger_all_stock(investor, account, old_security, new_security):
    """All-stock merger creates MERGER_OUT and MERGER_IN transactions."""
    # Buy 100 shares of old security
    Transactions.objects.create(
        investor=investor, account=account, security=old_security,
        type="Buy", date=date(2024, 1, 1), currency="USD",
        quantity=Decimal("100"), price=Decimal("50"),
    )
    result = execute_merger(
        investor, old_security.id, new_security.id, "2024-01-15",
        conversion_ratio="2", cash_per_share="0",
    )
    assert "merger" in result
    assert "accounts" in result
    assert len(result["accounts"]) == 1

    # Verify MERGER_OUT transaction was created
    out_txns = Transactions.objects.filter(
        investor=investor, security=old_security, type="Merger out"
    )
    assert out_txns.count() == 1
    assert out_txns[0].quantity == Decimal("-100")

    # Verify MERGER_IN transaction was created (200 new shares = 100 * ratio 2)
    in_txns = Transactions.objects.filter(
        investor=investor, security=new_security, type="Merger in"
    )
    assert in_txns.count() == 1
    assert in_txns[0].quantity == Decimal("200")


# =============================================================================
# execute_merger — all-cash merger execution
# =============================================================================


@pytest.mark.django_db
def test_execute_merger_all_cash(investor, account, old_security):
    """All-cash merger creates only MERGER_OUT with cash flow."""
    Transactions.objects.create(
        investor=investor, account=account, security=old_security,
        type="Buy", date=date(2024, 1, 1), currency="USD",
        quantity=Decimal("100"), price=Decimal("50"),
    )
    result = execute_merger(
        investor, old_security.id, None, "2024-01-15",
        conversion_ratio=None, cash_per_share="60",
    )
    # Verify merger_out transaction has the cash flow
    out_txn = Transactions.objects.get(type="Merger out")
    assert out_txn.cash_flow == Decimal("6000")  # 100 * 60

    # Verify only MERGER_OUT (no MERGER_IN for all-cash)
    out_txns = Transactions.objects.filter(type="Merger out")
    assert out_txns.count() == 1
    in_txns = Transactions.objects.filter(type="Merger in")
    assert in_txns.count() == 0


# =============================================================================
# execute_transfer — validation and execution (covers lines 313-430)
# =============================================================================


@pytest.mark.django_db
def test_execute_transfer_security_not_found(investor, account, second_account):
    """Non-existent security raises CorporateActionError with 404."""
    with pytest.raises(CorporateActionError) as exc_info:
        execute_transfer(investor, 99999, account.id, second_account.id, "10", "2024-01-15")
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_execute_transfer_account_not_found(investor, old_security, account):
    """Non-existent to_account raises CorporateActionError with 404."""
    with pytest.raises(CorporateActionError) as exc_info:
        execute_transfer(investor, old_security.id, account.id, 99999, "10", "2024-01-15")
    assert exc_info.value.status_code == 404


@pytest.mark.django_db
def test_execute_transfer_no_buy_in_price(investor, old_security, account, second_account):
    """Transfer without prior transactions raises CorporateActionError."""
    with pytest.raises(CorporateActionError, match="Unable to calculate buy-in price"):
        execute_transfer(
            investor, old_security.id, account.id, second_account.id, "10", "2024-01-15"
        )


@pytest.mark.django_db
def test_execute_transfer_success(investor, old_security, account, second_account):
    """Successful transfer creates transactions and moves position."""
    # Buy 100 shares first
    Transactions.objects.create(
        investor=investor, account=account, security=old_security,
        type="Buy", date=date(2024, 1, 1), currency="USD",
        quantity=Decimal("100"), price=Decimal("50"),
    )
    result = execute_transfer(
        investor, old_security.id, account.id, second_account.id, "10", "2024-01-15"
    )
    assert "message" in result
    assert result["transfer_value"] == Decimal("500")  # 10 shares * $50 buy-in price

    # Verify position moved: from_account should have 90, to_account should have 10
    from services.positions import position
    from_pos = position(old_security, date(2024, 1, 16), investor, account_ids=[account.id])
    to_pos = position(old_security, date(2024, 1, 16), investor, account_ids=[second_account.id])
    assert from_pos == Decimal("90")
    assert to_pos == Decimal("10")
