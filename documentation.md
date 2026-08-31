# Bank Statement Analyzer: Single Source of Truth

## 1. System Overview
The **Bank Statement Analyzer** is a financial web application primarily built with Django. Its original purpose is to allow users to authenticate, upload PDF bank statements (specifically focused on Nigerian banks), automatically extract and categorize transactions, and provide a general statistical analysis across all uploaded statements.

The system relies on a monolithic MVC (Model-View-Template) Django architecture for its backend, utilizing SQLite as its default database. Data extraction from PDFs is powered by `pdfplumber`. While the backend handles processing and server-side rendering with Tailwind CSS and Vanilla Chart.js, the repository also contains an unintegrated, scaffolded React + Vite setup (`src/`, `package.json`) which indicates an incomplete migration towards a single-page application (SPA) architecture.

## 2. Architecture & Data Flow

### Directory Structure & Major Decisions
- `core/`: The main Django application containing models, views, forms, and core business logic.
  - `core/parsers/`: Contains the parsing logic for extracting text from PDFs. Includes a universal parser and disconnected bank-specific stubs.
  - `core/services/`: Contains domain services like `UploadService` and `logging_service.py` to decouple business logic from views.
- `bankstatements/`: The Django project configuration folder (settings, urls, wsgi/asgi).
- `src/` & `package.json`: The unintegrated React 18 + Vite frontend scaffold.
- `templates/`: Django HTML templates utilizing Tailwind CSS and Chart.js.

### Data Flow
1. **Upload & Ingestion**: The user uploads a PDF statement via the UI (HTTP POST to `upload_statement` view).
2. **Validation & Hashing**: The `UploadService` validates the file. To prevent duplicate uploads, a SHA-256 hash is generated from the uploaded file's binary content.
3. **Parsing Data**:
   - The file is routed to `UniversalBankParser` which uses `pdfplumber` to read tabular transaction data.
   - Heavy regex patterns extract tabular fields: Date, Description, Amount (Credit/Debit), and Balance.
   - Built-in categorization logic matches keywords in transaction descriptions to pre-defined categories (e.g., "shoprite" -> "Food").
4. **Data Persistence**:
   - Parsed transactions generate a unique hash (`date|description|amount|balance`) to prevent partial duplicate entries.
   - Records are bulk-inserted into the SQLite database in an atomic transaction chunk.
5. **Aggregation & Visualization**:
   - The `/dashboard` view queries the database using Django ORM aggregation functions (`TruncMonth`, `Sum`, `Count`).
   - The aggregated statistics are passed as JSON strings directly into the Django template context where Chart.js renders the data on the client side.

## 3. Core Components & Code Logic

### Models (`core/models.py`)
- **`UploadedFile`**: Represents the uploaded PDF. Stores file metadata, computed `file_hash` (for deduplication), and transaction counts.
- **`Transaction`**: Represents individual ledger entries (Date, Amount, Category, Balance, Content Hash). Maintains a unique constraint tying the transaction to its `uploaded_file` and `content_hash`.
- **`Category`**: Manages system and user-defined transaction categories, storing `keyword_list` to match during parsing.

### Parsers (`core/parsers/`)
- **`BaseStatementParser`**: An abstract foundation providing shared utilities like `clean_amount`, volatile `parse_date` logic handling various fragmented Nigerian date formats, and `categorize_transaction` dictionary-based matching.
- **`UniversalBankParser`**: The primary workhorse of the app. It iterates through five distinct regex patterns (`_parse_pattern_1..5`) to identify columnar data and tabular structures.
- **Bank-Specific Parsers (`gtbank.py`, `uba.py`, etc.)**: These exist but are essentially disconnected stubs; the system defaults to routing all files through the universal parser via `__init__.py`.

### Services (`core/services/`)
- **`UploadService`**: Manages the upload lifecycle. Ensures ACID compliance using Django atomic transactions, processes duplicate transaction skipping, and handles bulk database writes.
- **`AuditLogger` (`logging_service.py`)**: A structured JSON logger with a `@log_exceptions` decorator to safely wrap view execution and capture exceptions seamlessly.

### Views (`core/views.py`)
- **`dashboard(request)`**: Calculates analytics (total spent, sum averages, grouping by week/month/category). Passes `DjangoJSONEncoder` parsed strings to the frontend.
- **`upload_statement(request)`**: The controller handling form submissions, invoking `UploadService`, and generating success/warning UI feedback.

## 4. Testing & Known Bugs Ledger

### Testing Status
**CRITICAL**: There are no underlying automated tests (no `tests.py` or `tests/` directory). Validating volatile regex logic across varying PDF layouts currently requires manual execution.

### Known Bugs & Weaknesses

| Bug / Vulnerability | Failure Point | Proposed Fix |
| :--- | :--- | :--- |
| **Silent Balance Integrity Failures** | `UniversalBankParser` tracks balance errors (`previous_balance + amount != current_balance`) by incrementing a counter but does not halt ingestion. Corrupt or misparsed data is still saved to the DB. | Implement a hard-fail or quarantine queue for statements with a balance error rate > 0%. Prompt the user for manual review. |
| **Regex Fragility** | The 5 regex patterns in `UniversalBankParser` can falsely identify line breaks, missing multi-line transaction descriptions typical in Nigerian bank statements. | Transition away from generic regex fallback. Implement header-detection to identify the originating bank and route to the specific parsers (e.g., `gtbank.py`). |
| **Date Parsing Anomaly (`BaseStatementParser`)** | If a date with a two-digit year is parsed >1 year into the future, the code subtracts 100 years. This logic mutates dates silently and error-prone. | Utilize robust date parsing libraries like `dateutil.parser` with specific `dayfirst=True` configurations, combined with context bounds based on the statement's stated period. |
| **Disconnected UI Architectures** | The frontend uses Django Templates but includes a scaffolded Vite+React setup (`src/`) which is entirely disconnected, confusing future scaling. | Choose one paradigm: Either purge the `src/` folder to stick with Django templates, or build DRF REST endpoints to fully transition to React. |

## 5. Revival Roadmap

Based on the current state of the codebase, here are the top prioritized steps to modernize and complete the project today:

1. **Establish a Test Suite (Immediate Priority)**
   * Implement `pytest`.
   * Gather 3-5 anonymized sample PDF statements from various Nigerian banks (GTBank, UBA, Zenith) and write unit tests for the regex patterns and `clean_amount`/`parse_date` parsers.
2. **Activate & Refine Bank-Specific Parsers**
   * Implement logic in `UploadService` to read the first page of the PDF to identify the issuing bank.
   * Route extraction logic directly to `gtbank.py`, `uba.py`, etc., rather than relying on the brute-force `UniversalBankParser`.
3. **Resolve Frontend Architecture Dissonance**
   * Decide on the presentation layer. To honor the React (`src/`) skeleton, install Django REST Framework (DRF) or Django Ninja.
   * Rewrite the `dashboard` and `upload_statement` views to expose JSON endpoints instead of rendering HTML templates.
4. **Fix Balance Integrity Engine**
   * Update the ingestion flow to rollback the atomic database transaction if the parser's checksum (`previous + amount == current`) fails on >2% of the rows, putting the file in a "requires manual mapping" status.
5. **Upgrade categorization (Optional Modernization)**
   * Replace the hardcoded keyword dictionary in `BaseStatementParser.categorize_transaction` with a simple LLM call or improved NLP engine to accurately map vague transaction descriptions to explicit categories.