from django.contrib import admin
from .models import UploadedFile, Transaction

@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('user', 'uploaded_at', 'transaction_count', 'processed')
    list_filter = ('processed', 'uploaded_at')
    search_fields = ('user__username',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'amount', 'category', 'balance')
    list_filter = ('category', 'date')
    search_fields = ('description',)