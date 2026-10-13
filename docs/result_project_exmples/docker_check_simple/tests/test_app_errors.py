"""Integration tests for temperature converter error handling."""
import pytest
from src.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestInvalidInputs:
    """Tests for invalid input handling — should show error message."""

    def test_empty_string(self, client):
        response = client.post(
            "/", data={"temperature": "", "direction": "C_TO_F"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()

    def test_non_numeric_abc(self, client):
        response = client.post(
            "/", data={"temperature": "abc", "direction": "C_TO_F"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()

    def test_non_numeric_xyz123(self, client):
        response = client.post(
            "/", data={"temperature": "xyz123", "direction": "F_TO_C"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()

    def test_special_chars_dollarsign(self, client):
        response = client.post(
            "/", data={"temperature": "$$$", "direction": "C_TO_F"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()

    def test_whitespace_only(self, client):
        response = client.post(
            "/", data={"temperature": "   ", "direction": "F_TO_C"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()

    def test_decimal_anomaly(self, client):
        response = client.post(
            "/", data={"temperature": "3.14.15", "direction": "C_TO_F"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()

    def test_special_chars_atselfhashpercent(self, client):
        response = client.post(
            "/", data={"temperature": "@#%", "direction": "F_TO_C"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "valid number" in data.lower()


class TestRegressionValidInputs:
    """Regression tests — valid inputs should still work after error handling."""

    def test_valid_c_to_f(self, client):
        response = client.post(
            "/", data={"temperature": "25", "direction": "C_TO_F"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "77.0" in data

    def test_valid_f_to_c(self, client):
        response = client.post(
            "/", data={"temperature": "32", "direction": "F_TO_C"}
        )
        assert response.status_code == 200
        data = response.data.decode()
        assert "0.0" in data
