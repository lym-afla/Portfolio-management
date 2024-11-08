from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('common', '0050_create_broker_account'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transactions',
            name='broker',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='common.brokers'),
        ),
        migrations.AlterField(
            model_name='fxtransaction',
            name='broker',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='common.brokers'),
        ),
        migrations.AlterField(
            model_name='annualperformance',
            name='broker',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='common.brokers'),
        ),
    ]
