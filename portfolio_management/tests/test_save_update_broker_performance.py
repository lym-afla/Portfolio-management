import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.utils import timezone
from datetime import date
from common.models import AnnualPerformance, Brokers, Transactions, Assets
from constants import CURRENCY_CHOICES, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_CASH_OUT
import json
import logging

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
    caplog.set_level(logging.INFO)  # Capture INFO level logs (and above)

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
    if response.status_code != 200:
        print(f"Response content: {response.content}")
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    # Parse the streaming response
    content = b''.join(response.streaming_content).decode('utf-8')
    events = [json.loads(line) for line in content.strip().split('\n')]

    # After processing the response
    print("\nDetailed events:")
    for event in events:
        print(json.dumps(event, indent=2))

    print("\nCaptured logs:")
    for record in caplog.records:
        print(f"{record.levelname}: {record.getMessage()}")

    # Check if we have the expected number of progress events and a complete event
    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    assert len(progress_events) == 1  # We expect one year of data
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
        'broker_or_group': str(broker.id),
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