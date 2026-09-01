from django.db import models
from django.contrib.auth.models import User
import hashlib


def calculate_file_hash(file) -> str:
    """Calculate SHA-256 hash of file content."""
    if not file:
        return ''
    sha256 = hashlib.sha256()
    file.seek(0)
    for chunk in iter(lambda: file.read(8192), b''):
        sha256.update(chunk)
    file.seek(0)
    return sha256.hexdigest()


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    keywords = models.TextField(blank=True, help_text="Comma-separated keywords for auto-categorization")
    is_system = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='unique_category_per_user'
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.split(',') if k.strip()]


class UploadedFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='statements/')
    file_hash = models.CharField(max_length=64, blank=True, db_index=True)
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    transaction_count = models.IntegerField(default=0)
    processing_errors = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'uploaded_at']),
            models.Index(fields=['user', 'file_hash']),
        ]

    def __str__(self):
        return f"Statement - {self.uploaded_at.strftime('%Y-%m-%d %H:%M')}"

    def calculate_file_hash(self):
        """Calculate SHA-256 hash of file content."""
        return calculate_file_hash(self.file)


class Transaction(models.Model):
    uploaded_file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField(db_index=True)
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['uploaded_file', 'date']),
            models.Index(fields=['category', 'date']),
            models.Index(fields=['uploaded_file', 'content_hash']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['uploaded_file', 'content_hash'],
                name='unique_transaction_per_file'
            ),
        ]

    def __str__(self):
        return f"{self.date} - {self.description[:30]} - ₦{self.amount}"

    @staticmethod
    def generate_content_hash(date, description, amount, balance):
        """Generate a unique hash for transaction content."""
        content = f"{date}|{description.strip()[:100]}|{amount}|{balance}"
        return hashlib.sha256(content.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if not self.content_hash:
            self.content_hash = self.generate_content_hash(
                self.date, self.description, self.amount, self.balance
            )
        super().save(*args, **kwargs)


class ChatMessage(models.Model):
    """Stores conversation history for the AI Copilot."""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    session_id = models.CharField(max_length=64, db_index=True, default='default')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['user', 'session_id', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.role}] {self.content[:50]}..."


@models.signals.post_delete.connect
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Automatically delete physical file from storage when UploadedFile record is deleted."""
    if sender == UploadedFile and instance.file:
        import os
        try:
            if os.path.isfile(instance.file.path):
                os.remove(instance.file.path)
        except Exception:
            pass