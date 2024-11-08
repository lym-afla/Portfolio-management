from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('common', '0049_assets_secid_alter_assets_data_source'),
    ]

    operations = [
        # Create BrokerAccounts model
        migrations.CreateModel(
            name='BrokerAccounts',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('native_id', models.CharField(help_text="Native account ID from broker's system", max_length=100)),
                ('name', models.CharField(help_text='Account name or description', max_length=100)),
                ('restricted', models.BooleanField(default=False)),
                ('comment', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('broker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='accounts', to='common.brokers')),
                ('investor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='broker_accounts', to='users.customuser')),
                ('securities', models.ManyToManyField(related_name='broker_accounts', to='common.assets')),
            ],
            options={
                'ordering': ['broker', 'name'],
                'unique_together': {('broker', 'native_id')},
            },
        ),
        
        # Add broker_account field to Transactions
        migrations.AddField(
            model_name='transactions',
            name='broker_account',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='common.brokeraccounts'),
        ),
        
        # Add broker_account field to FXTransaction
        migrations.AddField(
            model_name='fxtransaction',
            name='broker_account',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='fx_transactions', to='common.brokeraccounts'),
        ),
        
        # Add broker_account field to AnnualPerformance
        migrations.AddField(
            model_name='annualperformance',
            name='broker_account',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='annual_performance', to='common.brokeraccounts'),
        ),
    ]