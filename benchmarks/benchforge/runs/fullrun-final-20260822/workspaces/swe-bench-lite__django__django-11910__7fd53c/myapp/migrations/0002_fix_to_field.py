from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('myapp', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='modela',
            old_name='field_wrong',
            new_name='field_fixed',
        ),
        migrations.AlterField(
            model_name='modelb',
            name='field_fk',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='myapp.ModelA',
                to_field='field_fixed',  # ✅ Fixed: now points to new PK field name
            ),
        ),
    ]
