import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    async def test_root_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    async def test_api_health(self, client: AsyncClient):
        resp = await client.get("/api/v1/health/")
        assert resp.status_code == 200

    async def test_openapi_schema(self, client: AsyncClient):
        resp = await client.get("/api/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema
        assert schema["info"]["title"] == "NeuroDrug AI Platform"


class TestAuthEndpoints:
    async def test_login_with_invalid_creds(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            data={"username": "notexist@test.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    async def test_me_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
