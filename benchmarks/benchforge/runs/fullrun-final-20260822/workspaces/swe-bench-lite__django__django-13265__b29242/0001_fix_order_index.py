from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        # Add appropriate dependency, e.g., ('posts', '0001_initial'),
    ]

    operations = [
        migrations.AlterOrderWithRespectTo(
            name='lookimage',
            order_with_respect_to='look',
        ),
        migrations.AddIndex(
            model_name='lookimage',
            index=models.Index(fields=['look', '_order'], name='look_image_look_id_eaff30_idx'),
        ),
        # Remaining indexes (optional, for completeness)
        migrations.AddIndex(
            model_name='lookimage',
            index=models.Index(fields=['created_at'], name='look_image_created_f746cf_idx'),
        ),
        migrations.AddIndex(
            model_name='lookimage',
            index=models.Index(fields=['updated_at'], name='look_image_updated_aceaf9_idx'),
        ),
    ]
