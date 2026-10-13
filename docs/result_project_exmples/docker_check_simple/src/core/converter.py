"""Pure temperature conversion functions."""


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit, rounded to 1 decimal place."""
    return round((celsius * 9 / 5) + 32, 1)


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius, rounded to 1 decimal place."""
    return round((fahrenheit - 32) * 5 / 9, 1)
