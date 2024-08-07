$(document).ready(function() {
    
    $('#updateBrokerPerformanceDatabase').click(function() {
        console.log('update-broker-performance-database button clicked');
        $('#updateBrokerPerformanceDatabaseModal').modal('show');
    });

    $(document).on('submit', '#brokerPerformanceForm', function(event) {
        event.preventDefault();

        // Hide the form modal
        $('#updateBrokerPerformanceDatabaseModal').modal('hide');

        // Show progress modal
        $('#updateProgressModal').modal('show');
        $('#updateProgressBar').css('width', '0%').attr('aria-valuenow', 0).text('0%');
        $('#updateStatus').text('Initializing update...');

        var formData = new FormData(this);

        var xhr = new XMLHttpRequest();
        xhr.open('POST', "/database/update_broker_performance/", true);
        xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
        xhr.onprogress = function(e) {
            console.log('Progress event received');
            var lines = e.target.responseText.split('\n');
            var lastLine = lines[lines.length - 2]; // Last complete line
            if (lastLine) {
                console.log('Last line:', lastLine);
                var data = JSON.parse(lastLine);
                if (data.status === 'progress') {
                    $('#updateProgressBar').css('width', data.progress + '%').attr('aria-valuenow', data.progress).text(Math.round(data.progress) + '%');
                    $('#updateStatus').text(`Updating ${data.year} – ${data.currency} (Restricted: ${data.is_restricted}) (${data.current}/${data.total})`);
                } else if (data.status === 'complete') {
                    console.log('Update complete');
                    $('#updateProgressModal').modal('hide');
                    location.reload();
                } else if (data.status === 'error') {
                    console.error('Error:', data.message);
                    showError(data.message);
                    $('#updateProgressModal').modal('hide');
                }
            }
        };
        xhr.onerror = function() {
            console.error('XHR error');
            $('#updateProgressModal').modal('hide');
            showError('An error occurred during the update process.');
        };
        xhr.onload = function() {
            console.log('XHR loaded');
            if (xhr.status !== 200) {
                console.error('XHR status:', xhr.status);
                showError('An error occurred during the update process.');
            }
        };
        xhr.send(formData);
        console.log('XHR sent');
    });

    function showError(message) {
        let errorAlert = $('#errorAlert');
        if (errorAlert.length === 0) {
            errorAlert = $('<div id="errorAlert" class="alert alert-danger" role="alert"></div>');
            $('#updateBrokerPerformanceDatabaseModal .modal-body').prepend(errorAlert);
        }
        errorAlert.text(message).show();
    }

});