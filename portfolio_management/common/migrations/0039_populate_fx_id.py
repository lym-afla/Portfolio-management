from django.db import migrations

def populate_fx_id(apps, schema_editor):
    FX = apps.get_model('common', 'FX')
    db_alias = schema_editor.connection.alias
    for index, fx in enumerate(FX.objects.using(db_alias).all().order_by('date'), start=1):
        fx.id = index
        fx.save()

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0038_add_fx_id_field'),
    ]

    operations = [
        migrations.RunPython(populate_fx_id),
    ]