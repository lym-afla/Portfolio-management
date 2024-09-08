from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0037_alter_annualperformance_currency_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='fx',
            name='id',
            field=models.BigAutoField(null=True, blank=True),
        ),
    ]