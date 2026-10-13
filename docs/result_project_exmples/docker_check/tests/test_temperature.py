"""Unit tests for temperature conversion module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from temperature import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    get_temperature_category,
)


class TestCelsiusToFahrenheit:
    """Tests for celsius_to_fahrenheit function."""

    def test_freezing_point(self):
        """0 °C should be 32 °F."""
        assert celsius_to_fahrenheit(0) == 32.0

    def test_boiling_point(self):
        """100 °C should be 212 °F."""
        assert celsius_to_fahrenheit(100) == 212.0

    def test_intersection(self):
        """-40 °C should be -40 °F (scales intersect)."""
        assert celsius_to_fahrenheit(-40) == -40.0

    def test_precision_36_6(self):
        """36.6 °C should be 97.88 °F."""
        result = celsius_to_fahrenheit(36.6)
        assert abs(result - 97.88) < 0.001

    def test_precision_37(self):
        """37.0 °C should be 98.6 °F."""
        result = celsius_to_fahrenheit(37.0)
        assert abs(result - 98.6) < 0.001

    def test_negative_value(self):
        """-10 °C should be 14 °F."""
        assert celsius_to_fahrenheit(-10) == 14.0


class TestFahrenheitToCelsius:
    """Tests for fahrenheit_to_celsius function."""

    def test_freezing_point(self):
        """32 °F should be 0 °C."""
        assert fahrenheit_to_celsius(32) == 0.0

    def test_boiling_point(self):
        """212 °F should be 100 °C."""
        assert fahrenheit_to_celsius(212) == 100.0

    def test_intersection(self):
        """-40 °F should be -40 °C."""
        assert fahrenheit_to_celsius(-40) == -40.0

    def test_body_temperature(self):
        """98.6 °F should be 37.0 °C."""
        result = fahrenheit_to_celsius(98.6)
        assert abs(result - 37.0) < 0.001

    def test_mild_temperature(self):
        """68 °F should be 20 °C."""
        assert fahrenheit_to_celsius(68.0) == 20.0


class TestGetTemperatureCategory:
    """Tests for get_temperature_category function."""

    @pytest.mark.parametrize("celsius,expected", [
        (-10.0, "cold"),
        (-0.1, "cold"),
        (0.0, "warm"),
        (0.5, "warm"),
        (29.9, "warm"),
        (30.0, "warm"),
        (30.1, "hot"),
        (35.0, "hot"),
        (100.0, "hot"),
        (212.0, "hot"),
    ])
    def test_boundaries(self, celsius, expected):
        """Test temperature category boundaries."""
        assert get_temperature_category(celsius) == expected


class TestInvalidInput:
    """Tests for invalid input handling."""

    def test_string_input_c_to_f(self):
        """Non-numeric string should raise ValueError."""
        with pytest.raises((ValueError, TypeError)):
            celsius_to_fahrenheit("abc")

    def test_none_input_c_to_f(self):
        """None should raise ValueError."""
        with pytest.raises((ValueError, TypeError)):
            celsius_to_fahrenheit(None)

    def test_string_input_f_to_c(self):
        """Non-numeric string should raise ValueError."""
        with pytest.raises((ValueError, TypeError)):
            fahrenheit_to_celsius("invalid")

    def test_none_input_f_to_c(self):
        """None should raise ValueError."""
        with pytest.raises((ValueError, TypeError)):
            fahrenheit_to_celsius(None)

    def test_inf_value(self):
        """Infinity should raise ValueError."""
        import math
        with pytest.raises(ValueError):
            celsius_to_fahrenheit(float('inf'))

    def test_nan_value(self):
        """NaN should raise ValueError."""
        import math
        with pytest.raises(ValueError):
            celsius_to_fahrenheit(float('nan'))
