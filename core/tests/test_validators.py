"""
Unit tests for file validators.
"""
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from core.validators import (
    validate_file_size,
    validate_file_extension,
    validate_file_content_type,
    validate_uploaded_file,
    FileValidationError,
)


class FileValidatorsTest(TestCase):
    def test_validate_file_size_valid(self):
        file = SimpleUploadedFile("test.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")
        # Should not raise
        validate_file_size(file)

    def test_validate_file_size_exceeded(self):
        # Create dummy file > 10MB
        oversized = SimpleUploadedFile("big.pdf", b"x" * (11 * 1024 * 1024), content_type="application/pdf")
        with self.assertRaises(FileValidationError):
            validate_file_size(oversized)

    def test_validate_file_extension_valid(self):
        file = SimpleUploadedFile("statement.PDF", b"%PDF-1.4 content", content_type="application/pdf")
        validate_file_extension(file)

    def test_validate_file_extension_invalid(self):
        file = SimpleUploadedFile("statement.exe", b"malicious", content_type="application/octet-stream")
        with self.assertRaises(FileValidationError):
            validate_file_extension(file)

    def test_validate_file_content_type_valid_pdf_header(self):
        file = SimpleUploadedFile("statement.pdf", b"%PDF-1.7 actual pdf stream", content_type="application/pdf")
        validate_file_content_type(file)

    def test_validate_file_content_type_invalid_header(self):
        file = SimpleUploadedFile("fake.pdf", b"NOT_A_PDF_HEADER", content_type="application/pdf")
        with self.assertRaises(FileValidationError):
            validate_file_content_type(file)

    def test_validate_uploaded_file_valid(self):
        file = SimpleUploadedFile("statement.pdf", b"%PDF-1.4 good content", content_type="application/pdf")
        self.assertTrue(validate_uploaded_file(file))
