from django.contrib import admin
from .models import UploadedFile, Transaction, Category, ChatMessage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_system', 'description')
    list_filter = ('is_system',)
    search_fields = ('name', 'keywords', 'user__username')


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'original_filename', 'uploaded_at', 'transaction_count', 'processed')
    list_filter = ('processed', 'uploaded_at')
    search_fields = ('user__username', 'original_filename', 'file_hash')
    date_hierarchy = 'uploaded_at'
    readonly_fields = ('file_hash', 'uploaded_at')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'description', 'amount', 'category', 'balance', 'uploaded_file')
    list_filter = ('category', 'date')
    search_fields = ('description', 'notes', 'uploaded_file__user__username', 'content_hash')
    date_hierarchy = 'date'
    list_select_related = ('category', 'uploaded_file', 'uploaded_file__user')
    readonly_fields = ('content_hash', 'created_at', 'updated_at')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session_id', 'role', 'short_content', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('user__username', 'content', 'session_id')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)

    def short_content(self, obj):
        return obj.content[:80] + '...' if len(obj.content) > 80 else obj.content
    short_content.short_description = 'Content'