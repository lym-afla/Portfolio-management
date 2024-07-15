$(document).ready(function() {
    
    $('#updateBrokerPerformanceDatabase').click(function() {
        console.log('update-broker-performance-database button clicked');
        $('#updateBrokerPerformanceDatabaseModal').modal('show');
    });

    $(document).on('submit', '#brokerPerformanceForm', function(event) {
        event.preventDefault();
        $.ajax({
            type: 'POST',
            url: "/database/update_broker_performance/",
            data: $(this).serialize(),
            success: function(response) {
                if (response.success) {
                    $('#updateBrokerPerformanceDatabaseModal').modal('hide');
                    // Reload the summary-over-time table or update it dynamically
                    // $('#table-summary-over-time').load(location.href + " #table-summary-over-time > *");
                    location.reload();
                } else {
                    // Handle success response with error message
                    showError(response.error || 'An unknown error occurred.');
                }
            },
            error: function(xhr, status, error) {
                // Handle error response
                let errorMessage = xhr.responseJSON ? xhr.responseJSON.error : 'An unknown error occurred.';
                showError(errorMessage);
            }
        });
    });

    function showError(message) {
        // Show error message using an alert or modal
        let errorAlert = $('#errorAlert');
        if (errorAlert.length === 0) {
            errorAlert = $('<div id="errorAlert" class="alert alert-danger" role="alert"></div>');
            $('#updateBrokerPerformanceDatabaseModal .modal-body').prepend(errorAlert);
        }
        errorAlert.text(message).show();
    }
});