/**
 * HA-Dash Utilities
 * Reusable utility functions for API calls and UI operations
 */

/**
 * Fetch with automatic retry and exponential backoff
 * @param {string} url - The URL to fetch
 * @param {Object} options - Fetch options (method, headers, body, etc.)
 * @param {Object} retryConfig - Retry configuration
 * @param {number} retryConfig.maxRetries - Maximum number of retry attempts (default: 3)
 * @param {number} retryConfig.initialDelay - Initial delay in ms (default: 1000)
 * @param {number} retryConfig.maxDelay - Maximum delay in ms (default: 30000)
 * @param {number} retryConfig.backoffMultiplier - Multiplier for exponential backoff (default: 2)
 * @param {Function} retryConfig.onRetry - Callback called before each retry (receives attempt number and delay)
 * @returns {Promise<Response>} - The fetch response
 * @throws {Error} - Throws the last error if all retries fail
 */
async function fetchWithRetry(url, options = {}, retryConfig = {}) {
    const {
        maxRetries = 3,
        initialDelay = 1000,
        maxDelay = 30000,
        backoffMultiplier = 2,
        onRetry = null
    } = retryConfig;
    
    let lastError;
    let delay = initialDelay;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response = await fetch(url, options);
            
            // If response is OK, return it
            if (response.ok) {
                return response;
            }
            
            // For 4xx errors (client errors), don't retry
            if (response.status >= 400 && response.status < 500) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // For 5xx errors (server errors), store error and retry
            lastError = new Error(`HTTP ${response.status}: ${response.statusText}`);
            
        } catch (error) {
            lastError = error;
            
            // Don't retry on the last attempt
            if (attempt === maxRetries) {
                break;
            }
        }
        
        // Wait before retrying (except after the last attempt)
        if (attempt < maxRetries) {
            if (onRetry) {
                onRetry(attempt + 1, delay);
            }
            
            await sleep(delay);
            
            // Calculate next delay with exponential backoff
            delay = Math.min(delay * backoffMultiplier, maxDelay);
        }
    }
    
    // All retries failed, throw the last error
    throw lastError;
}

/**
 * Sleep for a specified duration
 * @param {number} ms - Duration in milliseconds
 * @returns {Promise<void>}
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Fetch JSON with retry logic
 * @param {string} url - The URL to fetch
 * @param {Object} options - Fetch options
 * @param {Object} retryConfig - Retry configuration (see fetchWithRetry)
 * @returns {Promise<Object>} - The parsed JSON response
 * @throws {Error} - Throws if fetch or JSON parsing fails
 */
async function fetchJsonWithRetry(url, options = {}, retryConfig = {}) {
    const response = await fetchWithRetry(url, options, retryConfig);
    return await response.json();
}

/**
 * Show a status message in the UI
 * @param {string} elementId - The ID of the element to update
 * @param {string} message - The message to display
 * @param {string} type - Message type: 'info', 'success', 'error', 'warning'
 */
function showStatus(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    element.textContent = message;
    
    // Remove existing status classes
    element.classList.remove('status-info', 'status-success', 'status-error', 'status-warning', 'status-running');
    
    // Add appropriate class based on type
    const classMap = {
        'info': 'status-info',
        'success': 'status-success',
        'running': 'status-running',
        'error': 'status-error',
        'warning': 'status-warning'
    };
    
    if (classMap[type]) {
        element.classList.add(classMap[type]);
    }
}

/**
 * Format a retry message
 * @param {number} attempt - The current attempt number
 * @param {number} delay - The delay before retry in ms
 * @returns {string} - Formatted message
 */
function formatRetryMessage(attempt, delay) {
    return `Retrying (attempt ${attempt}) in ${(delay / 1000).toFixed(1)}s...`;
}

// Export utilities for use in other modules
window.HADashUtils = {
    fetchWithRetry,
    fetchJsonWithRetry,
    sleep,
    showStatus,
    formatRetryMessage
};
