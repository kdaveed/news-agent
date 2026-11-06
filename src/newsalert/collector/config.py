"""Collector configuration. Separate from web Settings, which require a session secret."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The five RSS feeds selected in phase 1 (Codex probe, 2026-11-05).
FEEDS = {
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian_world": "https://www.theguardian.com/world/rss",
    "dw_world": "https://rss.dw.com/rdf/rss-en-world",
    "france24_en": "https://www.france24.com/en/rss",
    "aljazeera_en": "https://www.aljazeera.com/xml/rss/all.xml",
}


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSALERT_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/newsalert.db"  # shared with the web app
    data_dir: Path = Path("./data")  # raw GDELT, RSS XML, Wikipedia text
    # Wikimedia rejects User-Agents without contact details. Set this to your repository URL.
    http_user_agent: str = "newsalert-collector/0.1 (+https://github.com/; news alert prototype)"

    # Banding thresholds (independent outlets per window). Starting values, tuned on past days.
    auto_min_outlets: int = 100
    auto_min_rss: int = 2
    review_min_outlets: int = 30
    keep_clusters: int = 300  # clusters stored per run, by score

    # RSS confirmation: an RSS item confirms a cluster if URLs match, or if enough headline
    # terms are shared and the item was published within this many hours of the cluster.
    rss_min_shared_terms: int = 3
    rss_max_hours: int = 12
