# Generated by Django 5.0.1 on 2024-04-07 15:31

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Assets',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(max_length=10)),
                ('ISIN', models.CharField(max_length=12)),
                ('name', models.CharField(max_length=30)),
                ('currency', models.CharField(max_length=3)),
                ('exposure', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='Brokers',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=20)),
                ('country', models.CharField(max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='FX',
            fields=[
                ('date', models.DateField(primary_key=True, serialize=False)),
                ('USDEUR', models.DecimalField(decimal_places=4, max_digits=7)),
                ('USDGBP', models.DecimalField(decimal_places=4, max_digits=7)),
                ('CHFGBP', models.DecimalField(decimal_places=4, max_digits=7)),
                ('RUBUSD', models.DecimalField(decimal_places=4, max_digits=7)),
                ('PLNUSD', models.DecimalField(decimal_places=4, max_digits=7)),
            ],
        ),
        migrations.CreateModel(
            name='Prices',
            fields=[
                ('date', models.DateField(primary_key=True, serialize=False)),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('security', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prices', to='common.assets')),
            ],
        ),
        migrations.CreateModel(
            name='Transactions',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('currency', models.CharField(max_length=3)),
                ('type', models.CharField(max_length=30)),
                ('date', models.DateField()),
                ('quantity', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('cash_flow', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('commission', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('comment', models.TextField(blank=True, null=True)),
                ('broker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='common.brokers')),
                ('security', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='common.assets')),
            ],
        ),
    ]
