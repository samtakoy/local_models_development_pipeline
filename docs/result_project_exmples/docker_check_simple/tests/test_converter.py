"""Unit tests for temperature converter functions."""
import pytest
from core.converter import celsius_to_fahrenheit, fahrenheit_to_celsius


class TestCelsiusToFahrenheit:
    def test_0(self):
        assert celsius_to_fahrenheit(0) == 32.0

    def test_100(self):
        assert celsius_to_fahrenheit(100) == 212.0

    def test_neg40(self):
        assert celsius_to_fahrenheit(-40) == -40.0

    def test_37(self):
        assert celsius_to_fahrenheit(37) == 98.6

    def test_negative(self):
        assert celsius_to_fahrenheit(-10) == 14.0


class TestFahrenheitToCelsius:
    def test_212(self):
        assert fahrenheit_to_celsius(212) == 100.0

    def test_32(self):
        assert fahrenheit_to_celsius(32) == 0.0

    def test_neg40(self):
        assert fahrenheit_to_celsius(-40) == -40.0
