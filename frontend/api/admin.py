"""
Admin API client.
"""

from typing import Dict, List, Optional

import streamlit as st

from api.client import get_client, handle_http_error
from core.logging import get_logger

logger = get_logger(__name__)


def admin_get_analytics() -> Optional[Dict]:
    try:
        with get_client() as client:
            resp = client.get("/admin/analytics")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Admin analytics", logger))
        return None


def admin_list_users() -> List[Dict]:
    try:
        with get_client() as client:
            resp = client.get("/admin/users")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Admin list users", logger))
        return []


def admin_create_user(email: str, password: str, role: str = "user") -> Optional[Dict]:
    try:
        with get_client() as client:
            resp = client.post("/admin/users", json={"email": email, "password": password, "role": role})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Admin create user", logger))
        return None


def admin_update_user(
    user_id: int,
    *,
    email: Optional[str] = None,
    password: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[Dict]:
    payload: Dict[str, object] = {}
    if email is not None:
        payload["email"] = email
    if password is not None:
        payload["password"] = password
    if role is not None:
        payload["role"] = role
    if is_active is not None:
        payload["is_active"] = bool(is_active)
    if not payload:
        return None
    try:
        with get_client() as client:
            resp = client.put(f"/admin/users/{int(user_id)}", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Admin update user", logger))
        return None


def admin_delete_user(user_id: int) -> bool:
    try:
        with get_client() as client:
            resp = client.delete(f"/admin/users/{int(user_id)}")
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(handle_http_error(e, "Admin delete user", logger))
        return False


def admin_list_projects() -> List[Dict]:
    try:
        with get_client() as client:
            resp = client.get("/admin/projects")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(handle_http_error(e, "Admin list projects", logger))
        return []

