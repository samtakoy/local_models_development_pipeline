/**
 * Client-side script for temperature converter app.
 * Handles AJAX conversion, result display, error handling, and card color changes.
 */

document.addEventListener('DOMContentLoaded', function () {
    // Get DOM elements
    var tempInput = document.getElementById('temp-input');
    var convertBtn = document.getElementById('convert-btn');
    var resultArea = document.getElementById('result-area');
    var resultValue = document.getElementById('result-value');
    var errorArea = document.getElementById('error-area');
    var errorText = document.getElementById('error-text');
    var tempCard = document.getElementById('temp-card');
    var directionDisplay = document.getElementById('direction-display');

    // Application state
    var currentDirection = 'C_to_F';  // начальное состояние — совпадает с default select в HTML

    /**
     * Show an error message.
     * @param {string} message - Error message to display.
     */
    function showError(message) {
        resultArea.style.display = 'none';
        errorText.textContent = message;
        errorArea.style.display = 'block';
        tempCard.classList.remove('card-cold', 'card-warm', 'card-hot');
    }

    /**
     * Show the conversion result.
     * @param {string} value - The formatted result string (e.g., "97.9 °F").
     */
    function showResult(value) {
        errorArea.style.display = 'none';
        resultValue.textContent = value;
        resultArea.style.display = 'block';
    }

    /**
     * Clear both result and error displays, remove card color classes.
     */
    function clearResult() {
        resultArea.style.display = 'none';
        errorArea.style.display = 'none';
        tempCard.classList.remove('card-cold', 'card-warm', 'card-hot');
        currentDirection = 'C_to_F';
        directionDisplay.querySelector('span').textContent = '\u00B0C \u2192 \u00B0F';
    }

    /**
     * Apply the appropriate color class to the card based on temperature category.
     * @param {string} category - One of "cold", "warm", "hot".
     */
    function applyCardColor(category) {
        tempCard.classList.remove('card-cold', 'card-warm', 'card-hot');
        if (category === 'cold') {
            tempCard.classList.add('card-cold');
        } else if (category === 'warm') {
            tempCard.classList.add('card-warm');
        } else if (category === 'hot') {
            tempCard.classList.add('card-hot');
        }
    }

    /**
     * Toggle direction: C_to_F <-> F_to_C.
     * Update the display indicator and auto-convert if input is filled.
     */
    function toggleDirection() {
        if (currentDirection === 'C_to_F') {
            currentDirection = 'F_to_C';
        } else {
            currentDirection = 'C_to_F';
        }
        directionDisplay.querySelector('span').textContent =
            currentDirection === 'C_to_F' ? '\u00B0C \u2192 \u00B0F' : '\u00B0F \u2192 \u00B0C';
        if (tempInput.value.trim() !== '') {
            convertTemperature();
        }
    }

    /**
     * Main conversion function - called on button click or Enter key.
     */
    async function convertTemperature() {
        var value = tempInput.value.trim();

        // Empty check
        if (value === '') {
            showError('Пожалуйста, введите значение температуры');
            return;
        }

        // Client-side numeric validation
        if (!/^-?\d+(\.\d+)?$/.test(value)) {
            showError('Пожалуйста, введите корректное числовое значение');
            return;
        }

        // Disable button during request
        convertBtn.disabled = true;
        var originalText = convertBtn.textContent;
        convertBtn.textContent = 'Обработка...';

        // Hide previous results and errors
        resultArea.style.display = 'none';
        errorArea.style.display = 'none';

        try {
            var direction = currentDirection;
            var response = await fetch('/api/convert', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    value: parseFloat(value),
                    direction: direction
                })
            });

            var data = await response.json();

            if (response.ok && data.success) {
                showResult(data.result);
                applyCardColor(data.category);
            } else {
                showError(data.error || 'Ошибка конвертации');
            }
        } catch (error) {
            showError('Ошибка соединения с сервером');
        } finally {
            convertBtn.disabled = false;
            convertBtn.textContent = originalText;
        }
    }

    // Event: Click on convert button
    convertBtn.addEventListener('click', convertTemperature);

    // Event: Toggle direction button
    document.getElementById('toggle-direction').addEventListener('click', toggleDirection);

    // Event: Enter key in input field
    tempInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            convertTemperature();
        }
    });

    // Event: Escape key clears result and input
    tempInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            clearResult();
            tempInput.value = '';
        }
    });

    /**
     * Handle clicking on an example button.
     * @param {number} value - Temperature value to set in the input field.
     */
    function handleExampleClick(value) {
        tempInput.value = String(value);
        currentDirection = 'C_to_F';  // примеры всегда в Celsius
        directionDisplay.querySelector('span').textContent = '\u00B0C \u2192 \u00B0F';
        convertTemperature();
    }

    // Event: Click on example buttons
    var exampleButtons = document.querySelectorAll('.btn-example');
    exampleButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var val = parseFloat(this.getAttribute('data-value'));
            handleExampleClick(val);
        });
    });
});
