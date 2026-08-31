from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_remove_uploadedfile_bank_name_and_more'),
    ]

    operations = [
        # Add new fields to UploadedFile
        migrations.AddField(
            model_name='uploadedfile',
            name='file_hash',
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name='uploadedfile',
            name='original_filename',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='uploadedfile',
            name='file_size',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='uploadedfile',
            name='processing_errors',
            field=models.TextField(blank=True),
        ),
        
        # Add content_hash to Transaction
        migrations.AddField(
            model_name='transaction',
            name='content_hash',
            field=models.CharField(db_index=True, max_length=64, default=''),
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='uploadedfile',
            index=models.Index(fields=['user', 'uploaded_at'], name='core_upload_user_id_uploaded_idx'),
        ),
        migrations.AddIndex(
            model_name='uploadedfile',
            index=models.Index(fields=['user', 'file_hash'], name='core_upload_user_id_file_hash_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['uploaded_file', 'date'], name='core_trans_file_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['category', 'date'], name='core_trans_cat_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['uploaded_file', 'content_hash'], name='core_trans_file_hash_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['date'], name='core_trans_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['amount'], name='core_trans_amount_idx'),
        ),
    ]