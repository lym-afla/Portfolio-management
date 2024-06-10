# Generated by Django 5.0.1 on 2024-06-10 20:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0012_alter_transactions_quantity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transactions',
            name='quantity',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=15, null=True),
        ),
    ]
