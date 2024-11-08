from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('common', '0051_alter_broker_fields'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='annualperformance',
            name='either_broker_or_group',
        ),
        migrations.RemoveConstraint(
            model_name='annualperformance',
            name='not_both_broker_and_group',
        ),
        migrations.RemoveConstraint(
            model_name='annualperformance',
            name='unique_investor_broker_year_currency',
        ),
    ] 