"""
API client for analysis configurations (Milestone 4).
"""
from typing import Dict, List, Optional

from api.client import get_client, handle_http_error
from core.logging import get_logger

logger = get_logger(__name__)


def get_analysis_configs() -> List[Dict]:
    try:
        with get_client() as client:
            resp = client.get("/analysis-configs/")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Get analysis configurations", logger))
        return []


def get_default_config() -> Optional[Dict]:
    try:
        with get_client() as client:
            resp = client.get("/analysis-configs/default")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Get default configuration", logger))
        return None


def update_analysis_config(config_id: int, config_data: Dict) -> Optional[Dict]:
    try:
        with get_client() as client:
            resp = client.put(f"/analysis-configs/{config_id}", json=config_data)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Update analysis configuration", logger))
        return None


def create_analysis_config(config_data: Dict) -> Optional[Dict]:
    try:
        with get_client() as client:
            resp = client.post("/analysis-configs/", json=config_data)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Create analysis configuration", logger))
        return None


def delete_analysis_config(config_id: int) -> bool:
    try:
        with get_client() as client:
            resp = client.delete(f"/analysis-configs/{config_id}")
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(handle_http_error(e, "Delete analysis configuration", logger))
        return False


def set_default_analysis_config(config_id: int) -> bool:
    updated = update_analysis_config(config_id, {"is_default": True})
    return bool(updated)

