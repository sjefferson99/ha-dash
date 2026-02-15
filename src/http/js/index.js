/**
 * HA-Dash Configurator - Main JavaScript
 * Handles loading status from the API and updating the UI
 */

// Fetch status from API on page load
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update the DOM with the received data
        const statusElement = document.getElementById('server-status');
        const versionElement = document.getElementById('server-version');
        
        if (statusElement && data.status) {
            statusElement.textContent = data.status;
            // Add the status-running class if status is "running"
            if (data.status === 'running') {
                statusElement.classList.add('status-running');
            }
        }
        
        if (versionElement && data.version) {
            versionElement.textContent = data.version;
        }
        
        console.log('Status loaded successfully:', data);
        
    } catch (error) {
        console.error('Failed to load status:', error);
        
        // Update UI to show error state
        const statusElement = document.getElementById('server-status');
        const versionElement = document.getElementById('server-version');
        
        if (statusElement) {
            statusElement.textContent = 'Error';
            statusElement.style.color = '#f44336';
        }
        
        if (versionElement) {
            versionElement.textContent = 'N/A';
        }
    }
}

// Load status when the page is ready
document.addEventListener('DOMContentLoaded', loadStatus);
