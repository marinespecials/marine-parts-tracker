from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0007_invoice_invoice_type_invoice_supplier_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='status',
            field=models.CharField(choices=[
                ('DRAFT', 'Draft'),
                ('PENDING', 'Order - Pending'),
                ('PROCESSING', 'Order - Processing'),
                ('DELIVERED', 'Order - Delivered'),
                ('UNPAID', 'Invoice - Unpaid'),
                ('OVERDUE', 'Invoice - Overdue'),
                ('PAID', 'Invoice - Paid'),
                ('VOID', 'Void'),
            ], default='DRAFT', max_length=20),
        ),
    ]
