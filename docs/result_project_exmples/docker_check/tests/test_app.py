"""Integration tests for Flask application routes."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from app import create_app


@pytest.fixture
def app():
    """Create test Flask application."""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


# ============================================================
# Tests for GET / (main page)
# ============================================================

class TestIndexPage:
    """Tests for the index page route."""

    def test_index_page_returns_200(self, client):
        """Main page should return 200 status code."""
        response = client.get('/')
        assert response.status_code == 200

    def test_index_page_contains_expected_elements(self, client):
        """Index page should contain key HTML elements."""
        response = client.get('/')
        html = response.get_data(as_text=True)
        assert 'temp-input' in html
        assert 'toggle-direction' in html
        assert 'direction-display' in html
        assert 'examples-section' in html
        assert 'btn-example' in html
        assert 'Перевести' in html
        assert 'app.js' in html
        assert 'style.css' in html

    def test_examples_have_correct_values(self, client):
        """Example buttons should have correct data-value attributes."""
        response = client.get('/')
        html = response.get_data(as_text=True)

        # Check data-value attributes
        assert 'data-value="0"' in html
        assert 'data-value="36.6"' in html
        assert 'data-value="100"' in html

        # Check button texts
        assert 'Вода замерзает 0' in html
        assert 'Тело 36,6' in html
        assert 'Вода кипит 100' in html

    def test_toggle_direction_button_exists(self, client):
        """Toggle direction button should be present in the page."""
        response = client.get('/')
        html = response.get_data(as_text=True)

        assert '⇄' in html
        assert 'id="toggle-direction"' in html
        assert 'direction-display' in html

    def test_example_buttons_are_present(self, client):
        """Example buttons section should be present."""
        response = client.get('/')
        html = response.get_data(as_text=True)

        assert 'examples-section' in html
        assert '<button' in html


# ============================================================
# Tests for POST /api/convert - Valid data
# ============================================================

class TestConvertValid:
    """Tests for valid conversion API calls."""

    def test_celsius_to_fahrenheit_zero(self, client):
        """0 °C → 32.0 °F, category warm."""
        response = client.post('/api/convert', json={
            'value': 0,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert '32.0 °F' in data['result']
        assert data['direction'] == 'C_to_F'
        assert data['category'] == 'warm'

    def test_celsius_to_fahrenheit_boiling(self, client):
        """100 °C → 212.0 °F, category hot."""
        response = client.post('/api/convert', json={
            'value': 100,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert '212.0 °F' in data['result']
        assert data['category'] == 'hot'

    def test_fahrenheit_to_celsius(self, client):
        """212 °F → 100.0 °C."""
        response = client.post('/api/convert', json={
            'value': 212,
            'direction': 'F_to_C'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert '100.0 °C' in data['result']

    def test_boundary_cold(self, client):
        """-10 °C → 14.0 °F, cold category."""
        response = client.post('/api/convert', json={
            'value': -10,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['category'] == 'cold'
        assert '14.0 °F' in data['result']

    def test_boundary_warm(self, client):
        """36.6 °C → 97.9 °F, hot category (>30°C)."""
        response = client.post('/api/convert', json={
            'value': 36.6,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['category'] == 'hot'
        assert '97.9 °F' in data['result']

    def test_boundary_hot(self, client):
        """35 °C → hot category."""
        response = client.post('/api/convert', json={
            'value': 35,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['category'] == 'hot'

    def test_response_structure(self, client):
        """Response should have correct structure."""
        response = client.post('/api/convert', json={
            'value': 36.6,
            'direction': 'C_to_F'
        })
        data = response.get_json()
        assert 'success' in data
        assert 'result' in data
        assert 'direction' in data
        assert 'category' in data
        assert 'celsius_value' in data


# ============================================================
# Tests for POST /api/convert - Errors and validation
# ============================================================

class TestConvertInvalid:
    """Tests for invalid conversion API calls."""

    def test_empty_json(self, client):
        """Empty JSON body should return 400."""
        response = client.post('/api/convert', json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_non_numeric_value(self, client):
        """Non-numeric value should return 400."""
        response = client.post('/api/convert', json={
            'value': 'abc',
            'direction': 'C_to_F'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
        assert 'correct numeric value' in data['error'].lower()

    def test_invalid_direction(self, client):
        """Invalid direction should return 400."""
        response = client.post('/api/convert', json={
            'value': 36.6,
            'direction': 'X_to_Y'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_missing_direction(self, client):
        """Missing direction field should return 400."""
        response = client.post('/api/convert', json={
            'value': 36.6
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_missing_value(self, client):
        """Missing value field should return 400."""
        response = client.post('/api/convert', json={
            'direction': 'C_to_F'
        })
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False

    def test_invalid_json_body(self, client):
        """Invalid JSON body should not crash the app."""
        response = client.post(
            '/api/convert',
            data='not json',
            content_type='application/json'
        )
        assert response.status_code in (400, 415)

    def test_large_value(self, client):
        """Large value should be handled correctly."""
        response = client.post('/api/convert', json={
            'value': 1000,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    def test_negative_value(self, client):
        """Negative value should return cold category."""
        response = client.post('/api/convert', json={
            'value': -50,
            'direction': 'C_to_F'
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['category'] == 'cold'

    def test_no_json_content_type(self, client):
        """Request without JSON content type should return error."""
        response = client.post(
            '/api/convert',
            data='hello',
            content_type='text/plain'
        )
        assert response.status_code in (400, 415)
