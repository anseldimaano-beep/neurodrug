from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List


class Settings(BaseSettings):
    PROJECT_NAME: str = "NeuroDrug AI Platform"
    VERSION: str = "4.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(default="development")

    # Database
    POSTGRES_USER: str = Field(default="neurodrug_user")
    POSTGRES_PASSWORD: str = Field(default="neurodrug_pass")
    POSTGRES_DB: str = Field(default="neurodrug")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_SSL: bool = Field(default=False)

    @property
    def DATABASE_URL(self) -> str:
        base = (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        return f"{base}?ssl=require" if self.POSTGRES_SSL else base

    @property
    def DATABASE_URL_SYNC(self) -> str:
        base = (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        return f"{base}?sslmode=require" if self.POSTGRES_SSL else base

    # Redis / Celery
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2")

    # Auth
    SECRET_KEY: str = Field(default="neurodrug-dev-secret-key-replace-in-production-32chars")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # External APIs
    OPEN_TARGETS_API: str = "https://api.platform.opentargets.org/api/v4/graphql"
    STRING_API: str = "https://string-db.org/api"
    DGIDB_API: str = "https://dgidb.org/api/v2"
    CHEMBL_API: str = "https://www.ebi.ac.uk/chembl/api/data"
    UNIPROT_API: str = "https://rest.uniprot.org"
    GDC_API: str = "https://api.gdc.cancer.gov"
    CLINICAL_TRIALS_API: str = "https://clinicaltrials.gov/api/v2"
    PUBMED_BASE_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Neo4j (optional)
    NEO4J_URI: Optional[str] = Field(default=None)
    NEO4J_USER: Optional[str] = Field(default=None)
    NEO4J_PASSWORD: Optional[str] = Field(default=None)

    # MLflow
    MLFLOW_TRACKING_URI: str = Field(default="http://localhost:5000")

    # Observability
    SENTRY_DSN: Optional[str] = Field(default=None)
    OTEL_ENDPOINT: Optional[str] = Field(default=None)

    # ML
    MODEL_CHECKPOINT_DIR: str = Field(default="checkpoints")
    MODEL_REGISTRY_DIR: str = Field(default="model_registry")
    DEFAULT_TOP_K: int = 20
    RATE_LIMIT_PER_MINUTE: int = 60

    # CORS
    ALLOWED_ORIGINS: List[str] = Field(default=["http://localhost:3000"])

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
