# Generated manually for SifoDrive LMS Cohort description 165-char max constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('live_classes', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cohort',
            name='description',
            field=models.CharField(blank=True, max_length=165, verbose_name='Description'),
        ),
    ]
