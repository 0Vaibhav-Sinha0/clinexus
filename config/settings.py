from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================================
    # GROQ
    # ==========================================================

    groq_api_key: str = Field(
        ...,
        description="Groq API Key"
    )

    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq chat model"
    )

    # ==========================================================
    # EMBEDDINGS
    # ==========================================================

    embedding_provider: str = Field(
        default="vertex_ai",
        description="Embedding provider"
    )

    embedding_model: str = Field(
        default="text-embedding-005",
        description="Embedding model"
    )

    # ==========================================================
    # LANGSMITH
    # ==========================================================

    langsmith_api_key: str = Field(
        default="",
        description="LangSmith API Key"
    )

    langsmith_project: str = Field(
        default="Clinexus",
        description="LangSmith project"
    )

    langchain_tracing_v2: bool = Field(
        default=False,
        description="Enable LangSmith tracing"
    )

    # ==========================================================
    # GOOGLE CLOUD
    # ==========================================================

    gcp_project_id: str = Field(
        ...,
        description="GCP Project ID"
    )

    gcp_region: str = Field(
        default="us-central1",
        description="GCP Region"
    )

    gcs_bucket_name: str = Field(
        ...,
        description="Cloud Storage Bucket"
    )

    # ==========================================================
    # DATABASE
    # ==========================================================

    db_host: str = Field(...)

    db_port: int = Field(
        default=5432
    )

    db_name: str = Field(
        default="clinical_trial_db"
    )

    db_user: str = Field(...)

    db_password: str = Field(...)

    # ==========================================================
    # CLINICALTRIALS.GOV
    # ==========================================================

    clinical_trials_base_url: str = Field(
        default="https://clinicaltrials.gov/api/v2"
    )

    clinical_trials_page_size: int = Field(
        default=100
    )

    # ==========================================================
    # PUBMED
    # ==========================================================

    pubmed_base_url: str = Field(
        default="https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    )

    # ==========================================================
    # API
    # ==========================================================

    api_host: str = Field(
        default="0.0.0.0"
    )

    api_port: int = Field(
        default=8000
    )

    api_env: str = Field(
        default="development"
    )

    # ==========================================================
    # PROPERTIES
    # ==========================================================

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://"
            f"{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}"
            f"/{self.db_name}"
        )

    @property
    def is_production(self) -> bool:
        return self.api_env.lower() == "production"


settings = Settings()