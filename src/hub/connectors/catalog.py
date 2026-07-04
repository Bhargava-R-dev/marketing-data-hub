from __future__ import annotations

from importlib import import_module

from hub.connectors.base import BaseConnector
from hub.core.config import HubConfig

# id -> (module path, class name). Classes are imported lazily so optional SDK
# dependencies (google-ads, facebook-business) are only needed when configured.
ALL_CONNECTORS: dict[str, tuple[str, str]] = {
    "ga4": ("hub.connectors.ga4", "GA4Connector"),
    "gsc": ("hub.connectors.gsc", "SearchConsoleConnector"),
    "youtube": ("hub.connectors.youtube", "YouTubeConnector"),
    "google_ads": ("hub.connectors.google_ads", "GoogleAdsConnector"),
    "meta_ads": ("hub.connectors.meta_ads", "MetaAdsConnector"),
}


def connector_class(source: str) -> type[BaseConnector]:
    if source not in ALL_CONNECTORS:
        raise KeyError(f"unknown connector: {source!r}")
    module_path, cls_name = ALL_CONNECTORS[source]
    return getattr(import_module(module_path), cls_name)


def build_connector(source: str, config: HubConfig) -> BaseConnector:
    if source not in ALL_CONNECTORS:
        raise KeyError(f"unknown connector: {source!r}")
    if source not in config.connectors:
        raise KeyError(f"connector not configured: {source!r} (add it to config.yaml)")
    cls = connector_class(source)
    return cls(settings=config.connectors[source], secrets_dir=config.secrets_dir)
