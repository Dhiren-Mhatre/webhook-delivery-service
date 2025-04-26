// This file contains client-side functionality for the Webhook Delivery Service

document.addEventListener('DOMContentLoaded', function() {
    // Enable Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Validate JSON in textareas with the 'json-validate' class
    const jsonTextareas = document.querySelectorAll('textarea.json-validate');
    jsonTextareas.forEach(function(textarea) {
        textarea.addEventListener('blur', function() {
            try {
                if (textarea.value.trim() !== '') {
                    JSON.parse(textarea.value);
                    textarea.classList.remove('is-invalid');
                    textarea.classList.add('is-valid');
                }
            } catch (e) {
                textarea.classList.remove('is-valid');
                textarea.classList.add('is-invalid');
                
                // Add error message if not already present
                let nextSibling = textarea.nextSibling;
                let feedbackElement = null;
                
                while (nextSibling) {
                    if (nextSibling.classList && nextSibling.classList.contains('invalid-feedback')) {
                        feedbackElement = nextSibling;
                        break;
                    }
                    nextSibling = nextSibling.nextSibling;
                }
                
                if (!feedbackElement) {
                    feedbackElement = document.createElement('div');
                    feedbackElement.className = 'invalid-feedback';
                    textarea.parentNode.insertBefore(feedbackElement, textarea.nextSibling);
                }
                
                feedbackElement.textContent = 'Invalid JSON: ' + e.message;
            }
        });
    });

    // Copy-to-clipboard functionality for pre code blocks
    document.querySelectorAll('pre code').forEach(function(codeBlock) {
        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'btn btn-sm btn-outline-light copy-btn';
        copyButton.innerHTML = '<i class="fa fa-copy"></i>';
        copyButton.title = 'Copy to clipboard';
        
        // Position the button
        copyButton.style.position = 'absolute';
        copyButton.style.top = '0.5rem';
        copyButton.style.right = '0.5rem';
        
        // Add click handler
        copyButton.addEventListener('click', function() {
            const textToCopy = codeBlock.textContent;
            navigator.clipboard.writeText(textToCopy).then(function() {
                // Success feedback
                copyButton.innerHTML = '<i class="fa fa-check"></i>';
                copyButton.classList.add('btn-success');
                copyButton.classList.remove('btn-outline-light');
                
                // Reset after 2 seconds
                setTimeout(function() {
                    copyButton.innerHTML = '<i class="fa fa-copy"></i>';
                    copyButton.classList.remove('btn-success');
                    copyButton.classList.add('btn-outline-light');
                }, 2000);
            });
        });
        
        // Add button to the DOM
        const preElement = codeBlock.parentElement;
        preElement.style.position = 'relative';
        preElement.appendChild(copyButton);
    });

    // Auto-refresh for status pages
    const autoRefreshElements = document.querySelectorAll('[data-auto-refresh]');
    autoRefreshElements.forEach(function(element) {
        const refreshInterval = parseInt(element.dataset.autoRefresh, 10) || 10000; // Default to 10 seconds
        
        setInterval(function() {
            window.location.reload();
        }, refreshInterval);
    });
});
