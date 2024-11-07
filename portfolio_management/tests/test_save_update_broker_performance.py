import pytest
from channels.testing import HttpCommunicator
from channels.db import database_sync_to_async
from database.consumers import UpdateBrokerPerformanceConsumer
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.utils import timezone
from datetime import date, datetime, timedelta
from common.models import FX, AnnualPerformance, Brokers, Transactions, Assets
from constants import (
    CURRENCY_CHOICES, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL, 
    TRANSACTION_TYPE_CASH_IN, TRANSACTION_TYPE_CASH_OUT
)
import json
import logging

from core.portfolio_utils import get_last_exit_date_for_brokers, calculate_performance

User = get_user_model()

@pytest.fixture
def user():
    """Create test user"""
    return User.objects.create_user(username='testuser', password='testpass')

@pytest.fixture
def broker(user):
    """Create test broker"""
    return Brokers.objects.create(name='Test Broker', investor=user)

@pytest.fixture
def transactions(user, broker):
    asset = Assets.objects.create(
        type='Stock',
        ISIN='US0378331005',
        name='Apple Inc.',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.investors.add(user)
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
        quantity=Decimal('-10'),
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

@pytest.fixture
def fx_rates(user):
    # Create FX rates for the test period
    start_date = date(2010, 1, 1)
    # end_date = date(2023, 1, 1)
    # current_date = start_date
    # while current_date <= end_date:
    fx = FX.objects.create(date=start_date)
    fx.investors.add(user)
    fx.USDEUR = Decimal('1.15')
    fx.USDGBP = Decimal('1.25')
    fx.CHFGBP = Decimal('0.85')
    fx.RUBUSD = Decimal('65')
    fx.PLNUSD = Decimal('4')
    fx.save()
        # current_date += timedelta(days=1)

@pytest.mark.django_db(transaction=True)  # Use transaction=True to avoid db locks
@pytest.mark.asyncio
async def test_update_broker_performance_initial(user, broker, transactions, caplog):
    """Test initial broker performance calculation"""
    caplog.set_level(logging.INFO)
    
    communicator = HttpCommunicator(
        UpdateBrokerPerformanceConsumer.as_asgi(),
        "POST",
        "/database/api/update-broker-performance/sse/",
        body=json.dumps({
            'broker_or_group': 'Test Broker',
            'currency': 'USD',
            'is_restricted': 'False',
            'skip_existing_years': False,
            'effective_current_date': '2023-01-01'
        }).encode('utf-8')
    )

    communicator.scope['user'] = user
    response = await communicator.get_response()
    
    assert response['status'] == 200

    events = [
        json.loads(line)
        for line in response['body'].decode('utf-8').strip().split('\n')
    ]

    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    assert len(progress_events) == 1
    assert len(complete_events) == 1

    @database_sync_to_async
    def get_performance():
        return AnnualPerformance.objects.filter(
            investor=user,
            broker_group=broker.name,
            year=2022,
            currency='USD',
            restricted=False
        ).first()

    performance = await get_performance()

    assert performance is not None
    assert performance.bop_nav == Decimal('0')
    assert performance.eop_nav == Decimal('500')
    assert performance.invested == Decimal('1500')
    assert performance.cash_out == Decimal('-1200')
    assert performance.price_change == Decimal('200')

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_invalid_data(user):
    """Test broker performance calculation with invalid data"""
    communicator = HttpCommunicator(
        UpdateBrokerPerformanceConsumer.as_asgi(),
        "POST",
        "/database/api/update-broker-performance/sse/",
        body=json.dumps({
            'broker_or_group': 'invalid',
            'currency': 'INVALID',
            'is_restricted': 'INVALID',
            'skip_existing_years': 'not_a_boolean',
            'effective_current_date': '2023-01-01'
        }).encode('utf-8')
    )
    
    communicator.scope['user'] = user
    response = await communicator.get_response()
    
    assert response['status'] == 400
    response_data = json.loads(response['body'].decode('utf-8'))
    assert 'error' in response_data
    assert 'errors' in response_data

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_no_transactions(user, broker):
    """Test broker performance calculation with no transactions"""
    communicator = HttpCommunicator(
        UpdateBrokerPerformanceConsumer.as_asgi(),
        "POST",
        "/database/api/update-broker-performance/sse/",
        body=json.dumps({
            'broker_or_group': broker.name,
            'currency': 'USD',
            'is_restricted': 'False',
            'skip_existing_years': False,
            'effective_current_date': '2023-01-01'
        }).encode('utf-8')
    )

    communicator.scope['user'] = user
    response = await communicator.get_response()
    
    assert response['status'] == 200

    events = [
        json.loads(line)
        for line in response['body'].decode('utf-8').strip().split('\n')
    ]

    error_events = [event for event in events if event['status'] == 'error']
    assert len(error_events) == 1
    assert error_events[0]['message'] == 'No transactions found'

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_streaming(user, broker, transactions, fx_rates, capsys):
    """Test broker performance streaming with all currencies and restrictions"""
    print("Starting test_update_broker_performance_streaming")

    communicator = HttpCommunicator(
        UpdateBrokerPerformanceConsumer.as_asgi(),
        "POST",
        "/database/api/update-broker-performance/sse/",
        body=json.dumps({
            'broker_or_group': broker.name,
            'currency': 'All',
            'is_restricted': 'All',
            'skip_existing_years': False,
            'effective_current_date': '2023-01-01'
        }).encode('utf-8')
    )

    communicator.scope['user'] = user
    response = await communicator.get_response()
    
    assert response['status'] == 200

    events = [
        json.loads(line)
        for line in response['body'].decode('utf-8').strip().split('\n')
    ]

    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    # Verify progress events contain required fields
    for event in progress_events:
        assert 'status' in event
        assert 'current' in event
        assert 'progress' in event
        assert 'year' in event
        assert 'currency' in event
        assert 'is_restricted' in event

    assert len(complete_events) == 1

    captured = capsys.readouterr()
    print("============== Captured output: ==============")
    print(captured.out)

@pytest.mark.django_db
def test_get_last_exit_date_for_brokers(user, broker):
    asset = Assets.objects.create(
        type='Stock',
        ISIN='US1234567890',
        name='Test Stock',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.investors.add(user)
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
        type='Stock',
        ISIN='US1234567890',
        name='Test Stock',
        currency='USD',
        exposure='Equity',
        restricted=False
    )
    asset.investors.add(user)
    asset.brokers.add(broker)
    
    start_date = datetime(2022, 1, 1).date()
    end_date = datetime(2022, 12, 31).date()
    
    Transactions.objects.create(
        investor=user,
        broker=broker,
        date=start_date,
        type=TRANSACTION_TYPE_CASH_IN,
        cash_flow=Decimal('1000'),
        currency='USD'
    )
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
    Transactions.objects.create(
        investor=user,
        broker=broker,
        date=end_date,
        type=TRANSACTION_TYPE_CASH_OUT,
        cash_flow=Decimal('-1200'),
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
        print(f"Transaction: {t.date} {t.type} {t.quantity} {t.price} {t.currency}")

    print(f"Price change: {asset.realized_gain_loss(end_date, user, 'USD', broker_id_list=[broker.id], start_date=start_date)}")
    
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
    
    assert performance_data['invested'] == Decimal('1000')  # No cash inflows
    assert performance_data['cash_out'] == Decimal('-1200')  # No cash outflows
    assert performance_data['price_change'] == Decimal('500')  # (15 - 10) * 100

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_update_broker_performance_skip_existing(user, broker, caplog):
    """Test broker performance calculation with skip_existing_years=True"""
    print("\nStarting test_update_broker_performance_skip_existing")
    caplog.set_level(logging.INFO)

    # Create test data
    @database_sync_to_async
    def setup_test_data():
        # Create asset
        asset = Assets.objects.create(
            type='Stock',
            ISIN='US0378331005',
            name='Apple Inc.',
            currency='USD',
            exposure='Equity',
            restricted=False
        )
        asset.investors.add(user)
        asset.brokers.add(broker)

        # Create transactions for different years
        years = [2021, 2022, 2023]
        for year in years:
            Transactions.objects.create(
                investor=user,
                broker=broker,
                date=date(year, 1, 1),
                type=TRANSACTION_TYPE_CASH_IN,
                cash_flow=Decimal('1000'),
                currency='USD'
            )
            Transactions.objects.create(
                investor=user,
                broker=broker,
                date=date(year, 6, 1),
                type=TRANSACTION_TYPE_BUY,
                quantity=Decimal('10'),
                price=Decimal('100'),
                currency='USD',
                security=asset
            )
            Transactions.objects.create(
                investor=user,
                broker=broker,
                date=date(year, 12, 31),
                type=TRANSACTION_TYPE_SELL,
                quantity=Decimal('-10'),
                price=Decimal('120'),
                currency='USD',
                security=asset
            )

        # Create existing AnnualPerformance for 2022
        AnnualPerformance.objects.create(
            investor=user,
            broker_group=broker.name,
            year=2022,
            currency='USD',
            restricted=False,
            bop_nav=Decimal('1200'),
            eop_nav=Decimal('2400'),
            invested=Decimal('1000'),
            cash_out=Decimal('0'),
            price_change=Decimal('200'),
            capital_distribution=Decimal('0'),
            commission=Decimal('0'),
            tax=Decimal('0'),
            fx=Decimal('0'),
            tsr='20%'
        )

    await setup_test_data()
    print("Created transactions and existing AnnualPerformance")

    # Create communicator
    communicator = HttpCommunicator(
        UpdateBrokerPerformanceConsumer.as_asgi(),
        "POST",
        "/database/api/update-broker-performance/sse/",
        body=json.dumps({
            'broker_or_group': broker.name,
            'currency': 'USD',
            'is_restricted': 'False',
            'skip_existing_years': True,
            'effective_current_date': '2024-01-01'
        }).encode('utf-8')
    )

    communicator.scope['user'] = user
    response = await communicator.get_response()
    
    assert response['status'] == 200

    events = [
        json.loads(line)
        for line in response['body'].decode('utf-8').strip().split('\n')
    ]

    progress_events = [event for event in events if event['status'] == 'progress']
    complete_events = [event for event in events if event['status'] == 'complete']

    print(f"Number of progress events: {len(progress_events)}")
    print(f"Number of complete events: {len(complete_events)}")

    assert len(progress_events) == 2  # Progress events for 2021 and 2023
    assert len(complete_events) == 1

    @database_sync_to_async
    def get_performances():
        performance_2022 = AnnualPerformance.objects.filter(
            investor=user,
            broker_group=broker.name,
            year=2022,
            currency='USD',
            restricted=False
        ).first()

        performance_2021 = AnnualPerformance.objects.filter(
            investor=user,
            broker_group=broker.name,
            year=2021,
            currency='USD',
            restricted=False
        ).first()

        performance_2023 = AnnualPerformance.objects.filter(
            investor=user,
            broker_group=broker.name,
            year=2023,
            currency='USD',
            restricted=False
        ).first()

        return performance_2022, performance_2021, performance_2023

    performance_2022, performance_2021, performance_2023 = await get_performances()

    print(f"Performance 2023:")
    for k, v in performance_2023.__dict__.items():
        print(f"{k}: {v}")

    # Check if 2022 performance was not updated
    assert performance_2022 is not None
    assert performance_2022.bop_nav == Decimal('1200')
    assert performance_2022.eop_nav == Decimal('2400')
    assert performance_2022.invested == Decimal('1000')
    assert performance_2022.cash_out == Decimal('0')
    assert performance_2022.price_change == Decimal('200')

    # Check 2021 performance
    assert performance_2021 is not None
    assert performance_2021.bop_nav == Decimal('0')
    assert performance_2021.eop_nav == Decimal('1200')
    assert performance_2021.invested == Decimal('1000')
    assert performance_2021.cash_out == Decimal('0')
    assert performance_2021.price_change == Decimal('200')

    # Check 2023 performance
    assert performance_2023 is not None
    assert performance_2023.bop_nav == Decimal('2400')
    assert performance_2023.eop_nav == Decimal('3600')
    assert performance_2023.invested == Decimal('1000')
    assert performance_2023.cash_out == Decimal('0')
    assert performance_2023.price_change == Decimal('200')
