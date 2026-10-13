import pytest
from src.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_root_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_root_has_placeholder(client):
    response = client.get("/")
    data = response.data.decode()
    assert "Temperature Converter" in data or "starting" in data.lower()
