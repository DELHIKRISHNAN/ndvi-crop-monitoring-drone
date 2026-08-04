"""
Tests for backend/main.py (FastAPI endpoints)
=============================================
Uses httpx.AsyncClient with ASGITransport for FastAPI testing.
"""

import pytest
import httpx

from backend.main import app, API_KEY
from backend.database import init_db, engine
from sqlmodel import SQLModel


@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.drop_all(engine)
    init_db()
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    return {"X-API-Key": API_KEY}


@pytest.mark.anyio
class TestHealthEndpoint:
    async def test_health_check(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.anyio
class TestReadingsEndpoints:
    async def test_create_reading_requires_auth(self, client):
        resp = await client.post(
            "/api/readings",
            json={
                "lat": 28.6,
                "lon": 77.2,
            },
        )
        # Should fail with 403 (no API key) or 422 (validation)
        assert resp.status_code in (403, 422)

    async def test_create_and_list_reading(self, client, auth_headers):
        payload = {
            "lat": 28.6139,
            "lon": 77.2090,
            "ndvi_mean": 0.65,
            "soil_moisture": 42.5,
        }
        resp = await client.post("/api/readings", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["lat"] == pytest.approx(28.6139)

        resp = await client.get("/api/readings")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


@pytest.mark.anyio
class TestFieldsEndpoints:
    async def test_create_field(self, client, auth_headers):
        resp = await client.post(
            "/api/fields",
            json={
                "name": "Test Field A",
                "lat_center": 28.5,
                "lon_center": 77.1,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

    async def test_list_fields(self, client):
        resp = await client.get("/api/fields")
        assert resp.status_code == 200


@pytest.mark.anyio
class TestAlertsEndpoints:
    async def test_list_alerts(self, client):
        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
