from django.db import migrations
from django.db.models import Count

def migrate_brokers_to_accounts(apps, schema_editor):
    Brokers = apps.get_model('common', 'Brokers')
    BrokerAccounts = apps.get_model('common', 'BrokerAccounts')
    Transactions = apps.get_model('common', 'Transactions')
    FXTransaction = apps.get_model('common', 'FXTransaction')
    AnnualPerformance = apps.get_model('common', 'AnnualPerformance')
    CustomUser = apps.get_model('users', 'CustomUser')

    # Get or create system user
    system_user, _ = CustomUser.objects.get_or_create(
        username='system',
        defaults={
            'email': 'system@example.com',
            'is_active': False,
            'password': 'unusable'
        }
    )

    # Create dummy broker
    dummy_broker, _ = Brokers.objects.get_or_create(
        name='Legacy Broker System',
        investor=system_user,
        defaults={
            'country': 'N/A',
            'comment': 'Created during migration to broker accounts system',
            'restricted': False
        }
    )

    # Convert each existing broker to a broker account
    for old_broker in Brokers.objects.exclude(id=dummy_broker.id):
        # Create broker account
        broker_account = BrokerAccounts.objects.create(
            investor=old_broker.investor,
            broker=dummy_broker,
            name=old_broker.name,
            native_id=f"legacy_{old_broker.id}",
            restricted=old_broker.restricted,
            comment=old_broker.comment,
            is_active=True
        )

        # Update relationships
        Transactions.objects.filter(broker=old_broker).update(
            broker_account=broker_account,
            broker=None
        )
        
        FXTransaction.objects.filter(broker=old_broker).update(
            broker_account=broker_account,
            broker=None
        )
        
        # Handle AnnualPerformance records
        for perf in AnnualPerformance.objects.filter(broker=old_broker):
            # Check for potential duplicates
            existing = AnnualPerformance.objects.filter(
                investor=perf.investor,
                year=perf.year,
                currency=perf.currency,
                restricted=perf.restricted,
                broker_group=old_broker.name  # Using broker name as group
            ).first()

            if existing:
                # Merge the records
                existing.bop_nav += perf.bop_nav
                existing.invested += perf.invested
                existing.cash_out += perf.cash_out
                existing.price_change += perf.price_change
                existing.capital_distribution += perf.capital_distribution
                existing.commission += perf.commission
                existing.tax += perf.tax
                existing.fx += perf.fx
                existing.eop_nav += perf.eop_nav
                existing.save()
                # Delete the duplicate
                perf.delete()
            else:
                # No duplicate, just update the record
                perf.broker_account = broker_account
                perf.broker = None
                perf.broker_group = old_broker.name
                perf.save()

        # Handle securities
        securities = old_broker.securities.all()
        broker_account.securities.set(securities)
        old_broker.securities.clear()

    # Delete old brokers except dummy
    Brokers.objects.exclude(id=dummy_broker.id).delete()

def reverse_migrate(apps, schema_editor):
    BrokerAccounts = apps.get_model('common', 'BrokerAccounts')
    Brokers = apps.get_model('common', 'Brokers')
    CustomUser = apps.get_model('users', 'CustomUser')
    
    for account in BrokerAccounts.objects.all():
        broker = Brokers.objects.create(
            name=account.name,
            investor=account.investor,
            country='Unknown',
            restricted=account.restricted,
            comment=account.comment
        )

        broker.securities.set(account.securities.all())
        account.transactions.all().update(broker=broker)
        account.fx_transactions.all().update(broker=broker)
        
        # Handle AnnualPerformance carefully
        for perf in account.annual_performance.all():
            perf.broker = broker
            # Keep broker_group as is
            perf.save()
        
        account.delete()

    CustomUser.objects.filter(username='system').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('common', '0052_remove_annual_performance_constraints'),
    ]

    operations = [
        migrations.RunPython(migrate_brokers_to_accounts, reverse_migrate),
    ]