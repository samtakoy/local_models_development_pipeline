import logging
import os
import sys

from flask import Flask, render_template, request


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    )

    # Configure logging
    logger = logging.getLogger("temperature_converter")
    logger.setLevel(logging.INFO)

    fmt = "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    formatter = logging.Formatter(fmt)

    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(log_dir, "app.log"))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info("Temperature Converter application starting on port 8050")

    # Root route — handle GET and POST for temperature conversion
    @app.route("/", methods=["GET", "POST"])
    def index():
        from core.converter import celsius_to_fahrenheit, fahrenheit_to_celsius

        if request.method == "POST":
            temperature_str = request.form.get("temperature", "")
            direction = request.form.get("direction", "C_TO_F")

            logger = logging.getLogger("temperature_converter")

            try:
                temperature = float(temperature_str)
            except (ValueError, TypeError):
                logger.warning("Invalid input received: %r", temperature_str)
                return render_template(
                    "index.html", error="Please enter a valid number"
                )

            if direction == "F_TO_C":
                converted = fahrenheit_to_celsius(temperature)
                from_value = temperature
                unit_in, unit_out = "°F", "°C"
            else:
                converted = celsius_to_fahrenheit(temperature)
                from_value = temperature
                unit_in, unit_out = "°C", "°F"

            logger.info("%s %s = %.1f %s", from_value, unit_in, converted, unit_out)
            result = f"{from_value:.1f} {unit_in} = {converted:.1f} {unit_out}"
            return render_template("index.html", result=result)

        # GET request: empty form
        return render_template("index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=8050, debug=False)
