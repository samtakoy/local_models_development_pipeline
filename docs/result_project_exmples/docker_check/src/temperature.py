"""Module for temperature conversion and category classification."""

import math


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit.

    Args:
        celsius: Temperature in degrees Celsius (int or float).

    Returns:
        Temperature in degrees Fahrenheit.

    Raises:
        ValueError: If input is not a valid number.
    """
    if not isinstance(celsius, (int, float)):
        raise ValueError(f"Expected a numeric value, got {type(celsius).__name__}")
    if math.isinf(celsius) or math.isnan(celsius):
        raise ValueError("Temperature must be a finite number")
    return celsius * 9 / 5 + 32


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius.

    Args:
        fahrenheit: Temperature in degrees Fahrenheit (int or float).

    Returns:
        Temperature in degrees Celsius.

    Raises:
        ValueError: If input is not a valid number.
    """
    if not isinstance(fahrenheit, (int, float)):
        raise ValueError(f"Expected a numeric value, got {type(fahrenheit).__name__}")
    if math.isinf(fahrenheit) or math.isnan(fahrenheit):
        raise ValueError("Temperature must be a finite number")
    return (fahrenheit - 32) * 5 / 9


def get_temperature_category(celsius: float) -> str:
    """Get temperature category based on Celsius value.

    Args:
        celsius: Temperature in degrees Celsius.

    Returns:
        'cold' if celsius < 0,
        'warm' if 0 <= celsius <= 30,
        'hot' if celsius > 30.
    """
    if celsius < 0.0:
        return "cold"
    elif celsius <= 30.0:
        return "warm"
    else:
        return "hot"


def convert_temperature(value: float, direction: str) -> float:
    """Convert temperature based on direction.

    Args:
        value: Temperature value to convert.
        direction: 'C_to_F' or 'F_to_C'.

    Returns:
        Converted temperature value.

    Raises:
        ValueError: If direction is not recognized.
    """
    if direction == "C_to_F":
        return celsius_to_fahrenheit(value)
    elif direction == "F_to_C":
        return fahrenheit_to_celsius(value)
    else:
        raise ValueError(f"Invalid direction: {direction!r}. Expected 'C_to_F' or 'F_to_C'.")
