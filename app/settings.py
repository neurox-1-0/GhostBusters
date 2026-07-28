"""Application settings for GhostBusters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str = os.getenv("SERVICE_NAME", "ghostbusters")
    app_env: str = os.getenv("APP_ENV", "development").lower()
    static_dir: Path = Path(os.getenv("STATIC_DIR", "static"))
    database_url: str | None = os.getenv("DATABASE_URL")
    auth_persistence_path: Path = Path(os.getenv("AUTH_PERSISTENCE_PATH", ".runtime/auth_store.json"))
    redis_url: str | None = os.getenv("REDIS_URL")
    auth_required: bool = os.getenv("AUTH_REQUIRED", "false").lower() in {"1", "true", "yes"}
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "true" if os.getenv("APP_ENV", "development").lower() == "production" else "false").lower() in {"1", "true", "yes"}
    allow_insecure_http_demo: bool = os.getenv("ALLOW_INSECURE_HTTP_DEMO", "false").lower() in {"1", "true", "yes"}
    demo_mode_enabled: bool = os.getenv("DEMO_MODE_ENABLED", "false").lower() in {"1", "true", "yes"}
    allow_production_demo_mode: bool = os.getenv("ALLOW_PRODUCTION_DEMO_MODE", "false").lower() in {"1", "true", "yes"}
    secret_key: str | None = os.getenv("SECRET_KEY") or os.getenv("SESSION_SECRET") or None
    trust_proxy_headers: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in {"1", "true", "yes"}
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "ghostbusters_session")
    csrf_cookie_name: str = os.getenv("CSRF_COOKIE_NAME", "ghostbusters_csrf")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    login_rate_limit_attempts: int = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
    login_rate_limit_window_seconds: int = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))
    auth_endpoint_rate_limit_attempts: int = int(os.getenv("AUTH_ENDPOINT_RATE_LIMIT_ATTEMPTS", "60"))
    expensive_rate_limit_attempts: int = int(os.getenv("EXPENSIVE_RATE_LIMIT_ATTEMPTS", "30"))
    expensive_rate_limit_window_seconds: int = int(os.getenv("EXPENSIVE_RATE_LIMIT_WINDOW_SECONDS", "60"))
    invitation_expiry_hours: int = int(os.getenv("INVITATION_EXPIRY_HOURS", "24"))
    invitation_email_enabled: bool = os.getenv("INVITATION_EMAIL_ENABLED", "false").lower() in {"1", "true", "yes"}
    invitation_from_email: str | None = os.getenv("INVITATION_FROM_EMAIL") or None
    app_base_url: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    cors_allowed_origins: tuple[str, ...] = tuple(item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if item.strip())
    max_request_body_bytes: int = int(os.getenv("MAX_REQUEST_BODY_BYTES", "1048576"))
    auto_create_schema: bool = os.getenv("AUTO_CREATE_SCHEMA", "true").lower() in {"1", "true", "yes"}
    conftest_enabled: bool = os.getenv("CONFTEST_ENABLED", "true").lower() in {"1", "true", "yes"}
    conftest_executable: str = os.getenv("CONFTEST_EXECUTABLE", "conftest")
    conftest_policy_dir: Path = Path(os.getenv("CONFTEST_POLICY_DIR", "policies"))
    conftest_timeout_seconds: float = float(os.getenv("CONFTEST_TIMEOUT_SECONDS", "5"))
    minimum_policy_confidence: float = float(os.getenv("MINIMUM_POLICY_CONFIDENCE", "0.70"))
    external_retry_enabled: bool = os.getenv("EXTERNAL_RETRY_ENABLED", "true").lower() in {"1", "true", "yes"}
    external_retry_max_attempts: int = int(os.getenv("EXTERNAL_RETRY_MAX_ATTEMPTS", "3"))
    external_retry_initial_delay_seconds: float = float(os.getenv("EXTERNAL_RETRY_INITIAL_DELAY_SECONDS", "0.25"))
    external_retry_multiplier: float = float(os.getenv("EXTERNAL_RETRY_MULTIPLIER", "2"))
    external_retry_max_delay_seconds: float = float(os.getenv("EXTERNAL_RETRY_MAX_DELAY_SECONDS", "2"))
    external_retry_jitter_seconds: float = float(os.getenv("EXTERNAL_RETRY_JITTER_SECONDS", "0.10"))
    external_call_timeout_seconds: float = float(os.getenv("EXTERNAL_CALL_TIMEOUT_SECONDS", "5"))
    ai_enabled: bool = os.getenv("AI_ENABLED", "false").lower() in {"1", "true", "yes"}
    ai_provider: str = os.getenv("AI_PROVIDER", "gemini")
    gemini_enabled: bool = os.getenv("GEMINI_ENABLED", os.getenv("AI_ENABLED", "false")).lower() in {"1", "true", "yes"}
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    gemini_fallback_model: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
    gemini_api_version: str = os.getenv("GEMINI_API_VERSION", "v1")
    gemini_timeout_seconds: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
    gemini_max_retries: int = int(os.getenv("GEMINI_MAX_RETRIES", "2"))
    gemini_assisted_planning_enabled: bool = os.getenv("GEMINI_ASSISTED_PLANNING_ENABLED", os.getenv("AI_ENABLED", "false")).lower() in {"1", "true", "yes"}
    gemini_assistant_enabled: bool = os.getenv("GEMINI_ASSISTANT_ENABLED", "false").lower() in {"1", "true", "yes"}
    gemini_max_planning_steps: int = int(os.getenv("GEMINI_MAX_PLANNING_STEPS", "6"))
    gemini_temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.1"))
    ai_deterministic_fallback_enabled: bool = os.getenv(
        "AI_DETERMINISTIC_FALLBACK_ENABLED", "true"
    ).lower() in {"1", "true", "yes"}
    cloud_hunt_candidate_threshold: float = float(os.getenv("CLOUD_HUNT_CANDIDATE_THRESHOLD", "0.45"))
    cloud_hunt_high_confidence_threshold: float = float(os.getenv("CLOUD_HUNT_HIGH_CONFIDENCE_THRESHOLD", "0.75"))
    cloud_hunt_resource_age_days: int = int(os.getenv("CLOUD_HUNT_RESOURCE_AGE_DAYS", "60"))
    cloud_hunt_activity_lookback_days: int = int(os.getenv("CLOUD_HUNT_ACTIVITY_LOOKBACK_DAYS", "30"))
    cloud_hunt_utilization_lookback_days: int = int(os.getenv("CLOUD_HUNT_UTILIZATION_LOOKBACK_DAYS", "14"))
    cloud_hunt_low_cpu_threshold: float = float(os.getenv("CLOUD_HUNT_LOW_CPU_THRESHOLD", "10"))
    cloud_hunt_enabled: bool = os.getenv("CLOUD_HUNT_ENABLED", "true").lower() in {"1", "true", "yes"}
    cloud_hunt_schedule_enabled: bool = os.getenv("CLOUD_HUNT_SCHEDULE_ENABLED", "true").lower() in {"1", "true", "yes"}
    cloud_hunt_schedule_config_path: Path = Path(os.getenv("CLOUD_HUNT_SCHEDULE_CONFIG_PATH", ".runtime/cloud_hunt_schedules.json"))
    cloud_hunt_schedule_interval_seconds: int = int(os.getenv("CLOUD_HUNT_SCHEDULE_INTERVAL_SECONDS", "60"))
    cloud_hunt_schedule_retry_attempts: int = int(os.getenv("CLOUD_HUNT_SCHEDULE_RETRY_ATTEMPTS", "2"))
    scheduler_lock_ttl_seconds: int = int(os.getenv("SCHEDULER_LOCK_TTL_SECONDS", "120"))
    outcome_verification_config_path: Path = Path(os.getenv("OUTCOME_VERIFICATION_CONFIG_PATH", ".runtime/outcome_verifications.json"))
    aws_profile: str | None = os.getenv("AWS_PROFILE") or None
    aws_region: str | None = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or None
    aws_allowed_regions: tuple[str, ...] = tuple(item.strip() for item in os.getenv("AWS_ALLOWED_REGIONS", "").split(",") if item.strip())
    aws_cloudwatch_lookback_days: int = int(os.getenv("AWS_CLOUDWATCH_LOOKBACK_DAYS", "14"))
    aws_integration_config_path: Path = Path(os.getenv("AWS_INTEGRATION_CONFIG_PATH", ".runtime/aws_integrations.json"))
    github_integration_enabled: bool = os.getenv("GITHUB_INTEGRATION_ENABLED", "false").lower() in {"1", "true", "yes"}
    github_token: str | None = os.getenv("GITHUB_TOKEN") or None
    github_webhook_secret: str | None = os.getenv("GITHUB_WEBHOOK_SECRET") or None
    github_allowed_repositories: tuple[str, ...] = tuple(item.strip().lower() for item in os.getenv("GITHUB_ALLOWED_REPOSITORIES", "").split(",") if item.strip())
    github_api_base_url: str = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
    github_request_timeout_seconds: float = float(os.getenv("GITHUB_REQUEST_TIMEOUT_SECONDS", "10"))
    github_app_id: str | None = os.getenv("GITHUB_APP_ID") or None
    github_app_client_id: str | None = os.getenv("GITHUB_APP_CLIENT_ID") or None
    github_app_client_secret: str | None = os.getenv("GITHUB_APP_CLIENT_SECRET") or None
    github_app_private_key: str | None = os.getenv("GITHUB_APP_PRIVATE_KEY") or None
    github_app_private_key_path: Path | None = Path(os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")) if os.getenv("GITHUB_APP_PRIVATE_KEY_PATH") else None
    github_app_name: str | None = os.getenv("GITHUB_APP_NAME") or None
    github_app_callback_url: str | None = os.getenv("GITHUB_APP_CALLBACK_URL") or None
    github_app_state_ttl_seconds: int = int(os.getenv("GITHUB_APP_STATE_TTL_SECONDS", "600"))
    github_app_installation_token_ttl_seconds: int = int(os.getenv("GITHUB_APP_INSTALLATION_TOKEN_TTL_SECONDS", "300"))
    github_development_token_fallback: bool = os.getenv("GITHUB_DEVELOPMENT_TOKEN_FALLBACK", "false" if os.getenv("APP_ENV", "development").lower() == "production" else "true").lower() in {"1", "true", "yes"}
    github_integration_config_path: Path = Path(os.getenv("GITHUB_INTEGRATION_CONFIG_PATH", ".runtime/github_integrations.json"))
    jira_base_url: str | None = os.getenv("JIRA_BASE_URL") or None
    jira_email: str | None = os.getenv("JIRA_EMAIL") or None
    jira_api_token: str | None = os.getenv("JIRA_API_TOKEN") or os.getenv("JIRA_TOKEN") or None
    jira_request_timeout_seconds: float = float(os.getenv("JIRA_REQUEST_TIMEOUT_SECONDS", "10"))
    jira_integration_config_path: Path = Path(os.getenv("JIRA_INTEGRATION_CONFIG_PATH", ".runtime/jira_integrations.json"))
    github_demo_repository: str | None = os.getenv("GITHUB_DEMO_REPOSITORY") or None
    github_remediation_branch_prefix: str = os.getenv("GITHUB_REMEDIATION_BRANCH_PREFIX", "ghostbusters/remediation")
    github_create_real_pr: bool = os.getenv("GITHUB_CREATE_REAL_PR", "false").lower() in {"1", "true", "yes"}
    terraform_cli_enabled: bool = os.getenv("TERRAFORM_CLI_ENABLED", "false").lower() in {"1", "true", "yes"}
    terraform_binary: str = os.getenv("TERRAFORM_BINARY", "terraform")
    terraform_timeout_seconds: float = float(os.getenv("TERRAFORM_TIMEOUT_SECONDS", "60"))
    terraform_work_root: Path = Path(os.getenv("TERRAFORM_WORK_ROOT", ".runtime/terraform"))
    terraform_allow_init: bool = os.getenv("TERRAFORM_ALLOW_INIT", "false").lower() in {"1", "true", "yes"}
    terraform_allow_network: bool = os.getenv("TERRAFORM_ALLOW_NETWORK", "false").lower() in {"1", "true", "yes"}


settings = Settings()


def validate_startup_settings(config: Settings = settings) -> None:
    """Fail closed for deployment settings while preserving local/demo defaults."""
    if config.app_env != "production":
        return
    errors: list[str] = []
    if not config.auth_required:
        errors.append("AUTH_REQUIRED=true is required in production.")
    if not config.session_cookie_secure and not config.allow_insecure_http_demo:
        errors.append("SESSION_COOKIE_SECURE=true is required in production unless ALLOW_INSECURE_HTTP_DEMO=true.")
    if not config.secret_key or len(config.secret_key) < 32 or config.secret_key.lower() in {"change-me", "development", "dev-secret"}:
        errors.append("SECRET_KEY (or SESSION_SECRET) must be a non-default value of at least 32 characters.")
    if not config.database_url:
        errors.append("DATABASE_URL is required in production.")
    if not config.redis_url:
        errors.append("REDIS_URL is required in production.")
    if not config.cors_allowed_origins:
        errors.append("CORS_ALLOWED_ORIGINS must be explicitly configured in production.")
    if not config.trust_proxy_headers:
        errors.append("TRUST_PROXY_HEADERS=true is required behind an HTTPS-aware proxy.")
    if config.demo_mode_enabled and not config.allow_production_demo_mode:
        errors.append("DEMO_MODE_ENABLED must be false unless ALLOW_PRODUCTION_DEMO_MODE=true.")
    if config.github_integration_enabled and not config.github_webhook_secret:
        errors.append("GITHUB_WEBHOOK_SECRET is required when GitHub webhooks are enabled.")
    if config.github_development_token_fallback:
        errors.append("GITHUB_DEVELOPMENT_TOKEN_FALLBACK must be false in production; configure a GitHub App instead.")
    if config.auto_create_schema:
        errors.append("AUTO_CREATE_SCHEMA=false is required; use the versioned migration command.")
    if errors:
        raise RuntimeError("Production configuration validation failed: " + " ".join(errors))

