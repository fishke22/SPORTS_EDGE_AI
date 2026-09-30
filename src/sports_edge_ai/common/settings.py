from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from sports_edge_ai.common.root import ProjectPaths


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPORTS_EDGE_",
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    timezone: str = "Asia/Taipei"
    log_level: str = "INFO"
    project_root: Path | None = None
    the_odds_api_key: SecretStr | None = None
    the_odds_api_monthly_credit_budget: int = 450
    the_odds_api_region: str = "us"
    backblaze_b2_key_id: SecretStr | None = None
    backblaze_b2_application_key: SecretStr | None = None
    backblaze_b2_pointer_key_id: SecretStr | None = None
    backblaze_b2_pointer_application_key: SecretStr | None = None
    backblaze_b2_bucket_id: str | None = None
    backblaze_b2_bucket_name: str | None = None
    backblaze_b2_name_prefix: str = "sports-edge-ai/"
    backblaze_b2_no_payment_method_confirmed: bool = False
    backblaze_b2_zero_dollar_storage_cap_confirmed: bool = False
    backblaze_b2_zero_dollar_download_cap_confirmed: bool = False
    backblaze_b2_transaction_caps_confirmed: bool = False
    forward_current_min_interval_minutes: int = 180
    forward_scores_min_interval_minutes: int = 720
    forward_scores_days_from: int = 3
    operational_collection_stale_after_minutes: int = 150
    operational_research_stale_after_minutes: int = 150
    operational_budget_warning_fraction: float = 0.8

    def __init__(self, **values: Any) -> None:
        explicit_root = values.get("project_root")
        root = (
            Path(explicit_root).expanduser().resolve()
            if explicit_root is not None
            else ProjectPaths.discover().root
        )
        super().__init__(_env_file=root / ".env", **values)

    @cached_property
    def paths(self) -> ProjectPaths:
        root = self.project_root.resolve() if self.project_root else ProjectPaths.discover().root
        return ProjectPaths(root)
