"""HTTP client for the API Gateway (CRUD_Marketplace Lambda + DynamoDB).

This is the only part of the view that knows the backend URLs.
"""
import logging
import os

import requests

log = logging.getLogger("api_client")

# >>> PASTE HERE the "Invoke URL" of your API Gateway (AWS console ->
# API Gateway -> your API -> Stages). No trailing "/" and no "/usuarios/...".
API_URL = os.environ.get(
    "API_URL", "https://i4rsywszmf.execute-api.us-east-1.amazonaws.com/"
).rstrip("/")
TIMEOUT = 8  # seconds; avoids hanging forever if AWS does not answer

# Route names exactly as they are configured in API Gateway and the Lambda.
ROUTE_QUERY = "/usuarios/consultar"
ROUTE_ADD = "/usuarios/agregar"
ROUTE_UPDATE = "/usuarios/modificar"
ROUTE_DELETE = "/usuarios/eliminar"


class ApiError(Exception):
    """Error that is safe to show to the user (no internal details)."""


class DuplicateId(ApiError):
    """The Lambda answered 409: a user with that ID already exists."""


def _failure(action, status):
    """Readable error including the HTTP status, to know what AWS answered."""
    hint = ""
    if status in (403, 404):
        hint = " Check that API_URL in Utils/api_client.py is your API Gateway URL."
    return ApiError(f"{action} (HTTP {status}).{hint}")


def _clean(user):
    """boto3 rejects floats, but the Lambda returns 7771452085.0 and sending it
    back as-is would fail. Convert whole-number floats to int."""
    return {
        k: int(v) if isinstance(v, float) and v.is_integer() else v
        for k, v in user.items()
    }


def _request(method, route, **kwargs):
    try:
        resp = requests.request(method, API_URL + route, timeout=TIMEOUT, **kwargs)
    except requests.RequestException:
        raise ApiError("Could not connect to the data server.") from None
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400:
        # Server terminal only (never shown to the user).
        log.warning("%s %s -> %s %s", method, route, resp.status_code, resp.text[:200])
    return resp.status_code, data


def list_users():
    status, data = _request("GET", ROUTE_QUERY)
    if status != 200 or not isinstance(data, list):
        raise _failure("Could not load the user list", status)
    return data


def get_user(user_id):
    """Return the full user, or None if it does not exist."""
    status, data = _request("GET", ROUTE_QUERY, params={"id": user_id})
    if status == 404:
        return None
    if status != 200 or not isinstance(data, dict):
        raise _failure("Could not fetch the user", status)
    return data


def add_user(user):
    status, _ = _request("POST", ROUTE_ADD, json=_clean(user))
    if status == 409:  # the updated Lambda rejects repeated IDs
        raise DuplicateId("A user with that ID already exists.")
    if status != 200:
        raise _failure("Could not add the user", status)


def update_user(user):
    status, _ = _request("PUT", ROUTE_UPDATE, json=_clean(user))
    if status != 200:
        raise _failure("Could not save the user", status)


def delete_user(user_id):
    status, _ = _request("DELETE", ROUTE_DELETE, params={"id": user_id})
    if status != 200:
        raise _failure("Could not delete the user", status)
