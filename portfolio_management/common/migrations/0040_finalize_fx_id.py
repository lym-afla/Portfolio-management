from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0039_populate_fx_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='fx',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='fx',
            name='date',
            field=models.DateField(unique=True),
        ),
    ]