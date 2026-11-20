from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel


def test_docs_served(client: TestClient) -> None:
    """FR9: interactive API docs are served at /docs."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_openapi_lists_every_endpoint(client: TestClient) -> None:
    """FR9: the API docs cover every endpoint the app exposes."""
    spec = client.get("/openapi.json").json()
    # Update this set as stories add endpoints.
    assert set(spec["paths"]) == {"/healthz", "/orders/lookup", "/returns"}
    lookup = spec["paths"]["/orders/lookup"]["post"]
    assert "requestBody" in lookup
    assert set(lookup["responses"]) >= {"200", "404", "422"}
    returns = spec["paths"]["/returns"]["post"]
    assert "requestBody" in returns
    assert set(returns["responses"]) >= {"201", "404", "422"}
    assert set(spec["paths"]["/healthz"]["get"]["responses"]) >= {"200", "503"}


class _Probe(BaseModel):
    order_id: str
    quantity: int


def _add_probe_routes(client: TestClient) -> None:
    router = APIRouter()

    @router.post("/_probe")
    def probe(body: _Probe) -> dict[str, str]:
        return {"order_id": body.order_id}

    @router.get("/_boom")
    def boom() -> None:
        raise RuntimeError("secret internals")

    client.app.include_router(router)


def test_malformed_body_gives_validation_error(client: TestClient) -> None:
    """NFR3 / AD-6: a schema-violating body returns 422 VALIDATION_ERROR in the envelope."""
    _add_probe_routes(client)
    response = client.post("/_probe", json={"order_id": "ORD-1001", "quantity": "lots"})
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "quantity" in body["error"]["message"]


def test_invalid_json_gives_validation_error(client: TestClient) -> None:
    """NFR3 / AD-6: a body that isn't valid JSON returns 422 VALIDATION_ERROR."""
    _add_probe_routes(client)
    response = client.post(
        "/_probe", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    """NFR3 / AD-6: an unknown route returns 404 NOT_FOUND in the envelope."""
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "NOT_FOUND", "message": "The requested resource was not found."}
    }


def test_wrong_method_uses_envelope(client: TestClient) -> None:
    """NFR3 / AD-6: a wrong HTTP method returns 405 METHOD_NOT_ALLOWED in the envelope."""
    response = client.post("/healthz")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]


def test_unhandled_error_is_500_without_internals(client: TestClient) -> None:
    """NFR3 / AD-6: an unexpected exception returns 500 INTERNAL_ERROR without leaking details."""
    _add_probe_routes(client)
    response = client.get("/_boom")
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
    }
    assert "secret" not in response.text
