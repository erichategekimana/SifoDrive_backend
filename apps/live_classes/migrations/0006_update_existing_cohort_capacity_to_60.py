from django.db import migrations


def update_cohort_capacities(apps, schema_editor):
    Cohort = apps.get_model("live_classes", "Cohort")
    # Update cohorts with old default capacity 50 to 60
    Cohort.objects.filter(max_capacity=50).update(max_capacity=60)


def reverse_update_cohort_capacities(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("live_classes", "0005_cohort_identifier_cohort_sequence_number_and_more"),
    ]

    operations = [
        migrations.RunPython(update_cohort_capacities, reverse_update_cohort_capacities),
    ]
