
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    app_env: str = "development"
    frontend_origin: str = "http://localhost:3000"

    jwt_secret_key: str
    access_token_expire_minutes: int = 60

    # OpenAI configuration
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"

    # Document upload configuration
    max_upload_size_mb: int = 10
    max_pdf_pages: int = 20
    invoice_storage_dir: str = "storage/invoices"

    # Optional Tesseract tessdata directory
    tesseract_data_path: str | None = None

    # Privacy-first document processing
    privacy_mode: str = "hybrid"
    local_extraction_enabled: bool = True
    ai_fallback_enabled: bool = True
    ai_send_raw_documents: bool = False
    ai_send_supplier_names: bool = False
    ai_send_buyer_names: bool = False
    ai_send_trns: bool = False
    ai_send_addresses: bool = False
    ai_send_emails: bool = False
    ai_send_invoice_numbers: bool = False
    ai_send_full_line_descriptions: bool = False
    privacy_max_ai_input_chars: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
