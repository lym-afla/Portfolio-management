from django.db import migrations, models
from constants import ACCOUNT_TYPE_CHOICES, ACCOUNT_TYPE_ALL

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0057_remove_brokeraccounts_securities'),
    ]

    operations = [
        # Remove old constraint
        migrations.RemoveConstraint(
            model_name='annualperformance',
            name='unique_investor_broker_group_year_currency',
        ),

        # Remove old field
        migrations.RemoveField(
            model_name='annualperformance',
            name='broker_group',
        ),

        # Add new fields
        migrations.AddField(
            model_name='annualperformance',
            name='selection_type',
            field=models.CharField(
                max_length=10,
                choices=ACCOUNT_TYPE_CHOICES,
                default=ACCOUNT_TYPE_ALL
            ),
        ),
        migrations.AddField(
            model_name='annualperformance',
            name='selection_id',
            field=models.IntegerField(null=True, blank=True),
        ),

        # Add new constraints
        migrations.AddConstraint(
            model_name='annualperformance',
            constraint=models.UniqueConstraint(
                fields=['investor', 'year', 'currency', 'restricted', 'selection_type', 'selection_id'],
                name='unique_annual_performance'
            ),
        ),
        migrations.AddConstraint(
            model_name='annualperformance',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(selection_type=ACCOUNT_TYPE_ALL, selection_id__isnull=True) |
                    ~models.Q(selection_type=ACCOUNT_TYPE_ALL) & models.Q(selection_id__isnull=False)
                ),
                name='valid_annual_performance_selection'
            ),
        ),

        # Delete all existing data
        migrations.RunSQL(
            'DELETE FROM common_annualperformance;'
        ),
    ] 