"""Flask application for temperature converter."""

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template, request

from src.temperature import convert_temperature, get_temperature_category


def create_app(config=None):
    """Create and configure the Flask application.

    Args:
        config: Optional configuration dict.

    Returns:
        Configured Flask app instance.
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))  # goes up from src/

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
    )

    if config:
        app.config.update(config)

    # Configure logging
    app.logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    console_handler.setFormatter(console_format)
    app.logger.addHandler(console_handler)

    # File handler (RotatingFileHandler)
    log_dir = os.path.join(base_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app.log')
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1048576, backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(console_format)
    app.logger.addHandler(file_handler)

    @app.route('/')
    def index():
        """Render the main page."""
        return render_template('index.html')

    @app.route('/api/convert', methods=['POST'])
    def api_convert():
        """Handle temperature conversion API request."""
        # Step 1: Log incoming request
        data = request.get_json(silent=True)
        if data:
            app.logger.info(
                'Incoming POST request: %s',
                json.dumps({'value': str(data.get("value")), 'direction': str(data.get("direction"))})
            )

        # Step 2: Extract JSON data
        if data is None:
            app.logger.warning('Validation failed: empty or invalid JSON body')
            return jsonify({'success': False, 'error': 'Please provide a valid JSON body'}), 400

        # Step 3: Validate fields presence
        if 'value' not in data or 'direction' not in data:
            missing = []
            if 'value' not in data:
                missing.append('value')
            if 'direction' not in data:
                missing.append('direction')
            app.logger.warning('Validation failed: missing fields %s', ', '.join(missing))
            return jsonify({
                'success': False,
                'error': f'Missing required field(s): {", ".join(missing)}'
            }), 400

        # Step 4: Type conversion of value
        try:
            value = float(data['value'])
        except (ValueError, TypeError):
            app.logger.warning(
                'Validation failed: %r is not a valid numeric value', data['value']
            )
            return jsonify({
                'success': False,
                'error': 'Please enter a correct numeric value'
            }), 400

        # Step 5: Validate direction
        direction = data['direction']
        if direction not in ('C_to_F', 'F_to_C'):
            app.logger.warning(
                'Validation failed: invalid direction %r', direction
            )
            return jsonify({
                'success': False,
                'error': 'Invalid conversion direction'
            }), 400

        # Step 6-10: Convert and categorize
        try:
            result = convert_temperature(value, direction)
            rounded_result = round(result, 1)

            # Determine category: for C_to_F use input value (in °C),
            # for F_to_C calculate intermediate Celsius first
            if direction == "C_to_F":
                celsius_value = value
            else:
                celsius_value = (value - 32) * 5 / 9

            category = get_temperature_category(celsius_value)

            unit = '°F' if direction == 'C_to_F' else '°C'
            result_str = '{:.1f} {}'.format(rounded_result, unit)

            app.logger.info(
                'Conversion successful: %.1f °C → %.1f %s [%s]',
                celsius_value, rounded_result, unit, category
            )

            return jsonify({
                'success': True,
                'result': result_str,
                'direction': direction,
                'category': category,
                'celsius_value': celsius_value if direction == 'C_to_F' else round(celsius_value, 1)
            }), 200

        except Exception:
            app.logger.exception('Conversion ended with error')
            return jsonify({
                'success': False,
                'error': 'An internal error occurred'
            }), 500

    return app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app = create_app()
    app.logger.info('Starting application on port %d', port)
    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    except OSError:
        app.run(host='0.0.0.0', port=8051, debug=False)
