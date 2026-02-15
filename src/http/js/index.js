/**
 * HA-Dash Configurator - Main JavaScript
 * Handles loading status from the API and updating the UI
 */

// Fetch status from API on page load with retry logic
async function loadStatus() {
    const statusElement = document.getElementById('server-status');
    const versionElement = document.getElementById('server-version');
    
    // Clear any existing content and show loading
    if (statusElement) {
        statusElement.textContent = 'Loading...';
        statusElement.className = 'value';
    }
    if (versionElement) {
        versionElement.textContent = 'Loading...';
    }
    
    try {
        // Use fetchJsonWithRetry with custom retry configuration
        const data = await HADashUtils.fetchJsonWithRetry(
            '/api/status',
            {},
            {
                maxRetries: 3,
                initialDelay: 1000,
                maxDelay: 10000,
                backoffMultiplier: 2,
                onRetry: (attempt, delay) => {
                    const retryMsg = HADashUtils.formatRetryMessage(attempt, delay);
                    console.log('Status load failed, ' + retryMsg);
                    HADashUtils.showStatus('server-status', retryMsg, 'warning');
                }
            }
        );
        
        // Update the DOM with the received data
        if (statusElement && data.status) {
            HADashUtils.showStatus('server-status', data.status, data.status);
        }
        
        if (versionElement && data.version) {
            versionElement.textContent = data.version;
        }
        
        console.log('Status loaded successfully:', data);
        
    } catch (error) {
        console.error('Failed to load status after retries:', error);
        
        // Update UI to show error state with retry button
        if (statusElement) {
            // Clear existing content
            statusElement.textContent = '';
            statusElement.className = 'value status-error';
            
            // Create error text
            const errorText = document.createElement('span');
            errorText.textContent = 'Error';
            statusElement.appendChild(errorText);
            
            // Create retry button
            const retryButton = document.createElement('button');
            retryButton.textContent = 'Retry';
            retryButton.className = 'retry-button';
            retryButton.onclick = () => loadStatus();
            statusElement.appendChild(retryButton);
        }
        
        if (versionElement) {
            versionElement.textContent = 'N/A';
        }
    }
}

// Make loadStatus available globally for debugging
window.loadStatus = loadStatus;

// Load status when the page is ready
document.addEventListener('DOMContentLoaded', loadStatus);
