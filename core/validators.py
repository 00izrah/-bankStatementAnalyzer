from django.core.exceptions import ValidationError
from django.conf import settings
import os

try:
    import magic
except ImportError:
    magic = None

# Maximum file size (10 MB)
MAX_FILE_SIZE = getattr(settings, 'MAX_UPLOAD_SIZE', 10 * 1024 * 1024)

# Allowed MIME types
ALLOWED_MIME_TYPES = [
    'application/pdf',
]

# Allowed extensions
ALLOWED_EXTENSIONS = ['.pdf']


class FileValidationError(ValidationError):
    """Custom exception for file validation errors."""
    pass


def validate_file_size(file):
    """Validate that file size is within limits."""
    if file.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        file_mb = file.size / (1024 * 1024)
        raise FileValidationError(
            f'File size ({file_mb:.1f} MB) exceeds maximum allowed size ({max_mb:.1f} MB).'
        )


def validate_file_extension(file):
    """Validate file extension."""
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f'File extension "{ext}" is not allowed. Allowed extensions: {", ".join(ALLOWED_EXTENSIONS)}'
        )


def validate_file_content_type(file):
    """Validate file MIME type by reading file content."""
    # Read first 2048 bytes to detect file type
    file.seek(0)
    file_header = file.read(2048)
    file.seek(0)
    
    try:
        mime = magic.from_buffer(file_header, mime=True)
    except Exception:
        # Fallback if python-magic is not available
        mime = None
    
    if mime and mime not in ALLOWED_MIME_TYPES:
        raise FileValidationError(
            f'File type "{mime}" is not allowed. Only PDF files are accepted.'
        )
    
    # Additional check: PDF files should start with %PDF
    if not file_header.startswith(b'%PDF'):
        raise FileValidationError(
            'Invalid PDF file. The file does not appear to be a valid PDF document.'
        )


def validate_uploaded_file(file):
    """Run all file validations."""
    errors = []
    
    try:
        validate_file_size(file)
    except FileValidationError as e:
        errors.append(str(e.message))
    
    try:
        validate_file_extension(file)
    except FileValidationError as e:
        errors.append(str(e.message))
    
    try:
        validate_file_content_type(file)
    except FileValidationError as e:
        errors.append(str(e.message))
    
    if errors:
        raise FileValidationError(errors)
    
    return True