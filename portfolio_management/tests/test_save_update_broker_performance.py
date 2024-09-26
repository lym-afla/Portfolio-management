import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.utils import timezone
from datetime import date, datetime, timedelta
from common.models import AnnualPerformance, Brokers, Transactions, Assets
from constants import (
    CURRENCY_CHOICES, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, 
    TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_CASH_OUT
)
import json
import logging

from core.portfolio_utils import get_last_exit_date_for_brokers, calculate_performance

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user():
    return User.objects.create_user(username='testuser', password='testpass')

@pytest.fixture
def broker(user):
    return Brokers.objects.create(name='Test Broker', investor=user)

@pytest.fixture
def transactions(user, broker):
    asset = Assets.objects.create(
        investor=user,
        type='Stock',
        ISIN='US0378331005',
        name='Apple Inc.',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.brokers.add(broker)

    Transactions.objects.create(
        investor=user,
        broker=broker,
        date=date(2022, 1, 1),
        type=TRANSACTION_TYPE_CASH_IN,
        cash_flow=Decimal('1500'),
        currency='USD'
    )
    Transactions.objects.create(
        investor=user,
        broker=broker,
        date=date(2022, 1, 2),
        type=TRANSACTION_TYPE_BUY,
        quantity=Decimal('10'),
        price=Decimal('100'),
        currency='USD',
        security=asset
    )
    Transactions.objects.create(
        investor=user,
        broker=broker,
        date=date(2022, 8, 31),
        type=TRANSACTION_TYPE_SELL,
        quantity=Decimal('10'),
        price=Decimal('120'),
        currency='USD',
        security=asset
    )
    Transactions.objects.create(
        investor=user,
        broker=broker,
        date=date(2022, 9, 1),
        type=TRANSACTION_TYPE_CASH_OUT,
        cash_flow=Decimal('-1200'),
        currency='USD'
    )

@pytest.mark.django_db
def test_update_broker_performance(api_client, user, broker, transactions, caplog):
    caplog.set_level(logging.INFO)
    api_client.force_authenticate(user=user)
    url = reverse('database:update_broker_performance')

    # Set the effective current date in the session
    session = api_client.session
    session['effective_current_date'] = '2023-01-01'
    session.save()

    data = {
        'broker_or_group': 'Test Broker',
        'currency': 'USD',
        'is_restricted': 'False',
        'skip_existing_years': False
    }

    response = api_client.post(url, data)
    assert response.status_code == 200

    # Parse the streaming response
    content = b''.join(response.streaming_content).decode('utf-8')
    events = [json.loads(line) for line in content.strip().split('\n')]

    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    assert len(progress_events) == 1
    assert len(complete_events) == 1

    # Check if the AnnualPerformance instance was created
    performance = AnnualPerformance.objects.filter(
        investor=user,
        broker_group=broker.name,
        year=2022,
        currency='USD',
        restricted=False
    ).first()

    assert performance is not None
    assert performance.bop_nav == Decimal('0')
    assert performance.eop_nav == Decimal('300')  # 1500 (cash in) - 1000 (buy) + 1200 (sell) - 1200 (cash out) = 500
    assert performance.invested == Decimal('1500')  # 10 * 100
    assert performance.cash_out == Decimal('-1200')  # 10 * 120
    assert performance.price_change == Decimal('200')  # (120 - 100) * 10

    # Test updating existing data
    data['skip_existing_years'] = True
    response = api_client.post(url, data)
    assert response.status_code == 200

    content = b''.join(response.streaming_content).decode('utf-8')
    events = [json.loads(line) for line in content.strip().split('\n')]

    # Check if we have only a complete event (no progress events due to skipping)
    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    assert len(progress_events) == 0
    assert len(complete_events) == 1

    # If the test fails, print additional debug information
    if not AnnualPerformance.objects.filter(investor=user, broker=broker, year=2022, currency='USD', restricted=False).exists():
        print("AnnualPerformance instance was not created. Debug info:")
        print(f"User: {user}")
        print(f"Broker: {broker}")
        print(f"Transactions: {Transactions.objects.filter(investor=user, broker=broker).count()}")
        print(f"Events received: {events}")

@pytest.mark.django_db
def test_update_broker_performance_invalid_data(api_client, user):
    api_client.force_authenticate(user=user)
    url = reverse('database:update_broker_performance')

    data = {
        'broker_or_group': 'invalid',
        'currency': 'INVALID',
        'is_restricted': 'INVALID',
        'skip_existing_years': 'not_a_boolean'
    }

    response = api_client.post(url, data)
    assert response.status_code == 400
    assert 'error' in response.json()
    assert 'errors' in response.json()

@pytest.mark.django_db
def test_update_broker_performance_no_transactions(api_client, user, broker):
    api_client.force_authenticate(user=user)
    url = reverse('database:update_broker_performance')

    session = api_client.session
    session['effective_current_date'] = '2023-01-01'
    session.save()

    data = {
        'broker_or_group': broker.name,
        'currency': 'USD',
        'is_restricted': 'False',
        'skip_existing_years': False
    }

    response = api_client.post(url, data)
    assert response.status_code == 200

    content = b''.join(response.streaming_content).decode('utf-8')
    events = [json.loads(line) for line in content.strip().split('\n')]

    error_events = [event for event in events if event['status'] == 'error']
    assert len(error_events) == 1
    assert error_events[0]['message'] == 'No transactions found'

@pytest.mark.django_db
@pytest.mark.parametrize("broker_or_group, currency, is_restricted, skip_existing_years", [
    ("All", "USD", "All", True),
    ("Test Broker", "EUR", "True", False),
    ("Group1", "All", "False", True),
    ("Test Broker", "GBP", "None", False),
])
def test_update_broker_performance_combinations(api_client, user, broker, transactions, broker_or_group, currency, is_restricted, skip_existing_years):
    api_client.force_authenticate(user=user)
    url = reverse('database:update_broker_performance')

    session = api_client.session
    session['effective_current_date'] = '2023-01-01'
    session.save()

    data = {
        'broker_or_group': broker_or_group,
        'currency': currency,
        'is_restricted': is_restricted,
        'skip_existing_years': skip_existing_years,
    }
    response = api_client.post(url, data)
    assert response.status_code == 200

    content = b''.join(response.streaming_content).decode('utf-8')
    events = [json.loads(line) for line in content.strip().split('\n')]

    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    assert len(complete_events) == 1
    if broker_or_group != "All" and currency != "All":
        assert len(progress_events) > 0

@pytest.mark.django_db
def test_update_broker_performance_streaming(api_client, user, broker, transactions):
    api_client.force_authenticate(user=user)
    url = reverse('database:update_broker_performance')

    session = api_client.session
    session['effective_current_date'] = '2023-01-01'
    session.save()

    data = {
        'broker_or_group': 'All',
        'currency': 'All',
        'is_restricted': 'All',
        'skip_existing_years': False,
    }
    response = api_client.post(url, data)
    assert response.status_code == 200
    
    content = b''
    for chunk in response.streaming_content:
        content += chunk
        progress_data = json.loads(chunk.decode('utf-8').strip())
        
        if progress_data['status'] == 'progress':
            assert 'current' in progress_data
            assert 'total' in progress_data
            assert 'progress' in progress_data
            assert 'year' in progress_data
            assert 'currency' in progress_data
            assert 'is_restricted' in progress_data
        elif progress_data['status'] == 'complete':
            break
        elif progress_data['status'] == 'error':
            pytest.fail(f"Error in streaming: {progress_data['message']}")

    assert b'{"status": "complete"}' in content

@pytest.mark.django_db
def test_get_last_exit_date_for_brokers(user, broker):
    asset = Assets.objects.create(
        investor=user,
        type='Stock',
        ISIN='US1234567890',
        name='Test Stock',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.brokers.add(broker)
    
    transaction_date = datetime.now().date() - timedelta(days=30)
    Transactions.objects.create(
        investor=user,
        broker=broker,
        security=asset,
        date=transaction_date,
        type=TRANSACTION_TYPE_BUY,
        quantity=100,
        price=10,
        currency='USD'
    )
    
    current_date = datetime.now().date()
    last_exit_date = get_last_exit_date_for_brokers([broker.id], current_date)
    
    assert last_exit_date == current_date

    # Close the position
    Transactions.objects.create(
        investor=user,
        broker=broker,
        security=asset,
        date=current_date - timedelta(days=1),
        type=TRANSACTION_TYPE_SELL,
        quantity=-100,
        price=15,
        currency='USD'
    )
    
    last_exit_date = get_last_exit_date_for_brokers([broker.id], current_date)
    assert last_exit_date == current_date - timedelta(days=1)

@pytest.mark.django_db
def test_calculate_performance(user, broker, caplog):

    caplog.set_level(logging.DEBUG)
    
    asset = Assets.objects.create(
        investor=user,
        type='Stock',
        ISIN='US1234567890',
        name='Test Stock',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.brokers.add(broker)
    
    start_date = datetime(2022, 1, 1).date()
    end_date = datetime(2022, 12, 31).date()
    
    Transactions.objects.create(
        investor=user,
        broker=broker,
        security=asset,
        date=start_date + timedelta(days=30),
        type=TRANSACTION_TYPE_BUY,
        quantity=100,
        price=10,
        currency='USD'
    )
    Transactions.objects.create(
        investor=user,
        broker=broker,
        security=asset,
        date=end_date - timedelta(days=30),
        type=TRANSACTION_TYPE_SELL,
        quantity=-100,
        price=15,
        currency='USD'
    )
    
    performance_data = calculate_performance(
        user,
        start_date,
        end_date,
        [broker.id],
        'USD'
    )

    for t in Transactions.objects.filter(investor=user, broker=broker):
        print(f"Transaction: {t.date} {t.security.name} {t.type} {t.quantity} {t.price} {t.currency}")

    print(f"Price change: {asset.realized_gain_loss(end_date, 'USD', broker_id_list=[broker.id], start_date=start_date)}")
    
    assert 'bop_nav' in performance_data
    assert 'eop_nav' in performance_data
    assert 'invested' in performance_data
    assert 'cash_out' in performance_data
    assert 'price_change' in performance_data
    assert 'capital_distribution' in performance_data
    assert 'commission' in performance_data
    assert 'tax' in performance_data
    assert 'fx' in performance_data
    assert 'tsr' in performance_data
    
    assert performance_data['invested'] == Decimal('0')  # No cash inflows
    assert performance_data['cash_out'] == Decimal('0')  # No cash outflows
    assert performance_data['price_change'] == Decimal('500')  # (15 - 10) * 100