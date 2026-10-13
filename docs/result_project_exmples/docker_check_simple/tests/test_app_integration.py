"""Integration tests for temperature converter web interface."""
import pytest
from src.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestRootGet:
    def test_root_returns_200_get(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_root_has_form_elements(self, client):
        response = client.get("/")
        data = response.data.decode()
        assert "temperature" in data
        assert "direction" in data
        assert "Перевести" in data


class TestConvertCelsiusToFahrenheit:
    def test_convert_c_to_f_25(self, client):
        response = client.post("/", data={
            "temperature": "25",
            "direction": "C_TO_F",
        })
        assert response.status_code == 200
        data = response.data.decode()
        assert "77.0" in data

    def test_convert_c_to_f_0(self, client):
        response = client.post("/", data={
            "temperature": "0",
            "direction": "C_TO_F",
        })
        assert response.status_code == 200
        data = response.data.decode()
        assert "32.0" in data

    def test_convert_c_to_f_100(self, client):
        response = client.post("/", data={
            "temperature": "100",
            "direction": "C_TO_F",
        })
        assert response.status_code == 200
        data = response.data.decode()
        assert "212.0" in data

    def test_convert_c_to_f_neg40(self, client):
        response = client.post("/", data={
            "temperature": "-40",
            "direction": "C_TO_F",
        })
        assert response.status_code == 200
        data = response.data.decode()
        assert "-40.0" in data


class TestConvertFahrenheitToCelsius:
    def test_convert_f_to_c_212(self, client):
        response = client.post("/", data={
            "temperature": "212",
            "direction": "F_TO_C",
        })
        assert response.status_code == 200
        data = response.data.decode()
        assert "100.0" in data

    def test_convert_f_to_c_37(self, client):
        """Convert 98.6 °F to Celsius: should show 37.0."""
        response = client.post("/", data={
            "temperature": "98.6",
            "direction": "F_TO_C",
        })
        assert response.status_code == 200
        data = response.data.decode()
        assert "37.0" in data
