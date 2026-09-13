# Generated manually for AccountStatus.BLACKLISTED support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE', 'Active'),
                    ('PENDING_VERIFICATION', 'Pending Phone Verification'),
                    ('SUSPENDED', 'Suspended'),
                    ('DEACTIVATED', 'Deactivated'),
                    ('BLACKLISTED', 'Blacklisted'),
                ],
                db_index=True,
                default='PENDING_VERIFICATION',
                max_length=30,
                verbose_name='Account Status',
            ),
        ),
    ]
