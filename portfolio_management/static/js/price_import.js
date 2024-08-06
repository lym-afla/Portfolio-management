$(document).ready(function() {

    $('#import_prices').on('click', function() {
        $('#importPricesModal').modal('show');
    });

    $('#submitImportPrices').on('click', function() {
        var formData = new FormData($('#importPricesForm')[0]);

        showSpinner();

        $.ajax({
            url: 'import_prices/',
            type: 'POST',
            data: formData,
            headers: {
                'X-CSRFToken': getCookie('csrftoken') // Add CSRF token to headers
            },
            processData: false,
            contentType: false,
            success: function(response) {
                // Clear previous errors
                $('.error-message').html('');

                hideSpinner();

                if (response.status === 'success') {

                    // Populate modal body with response details
                    var detailsHtml = '<ul>';
                    response.details.forEach(function(detail) {
                        detailsHtml += '<li>' + detail + '</li>';
                    });
                    detailsHtml += '</ul>';

                    $('#successModal .modal-body').html(detailsHtml);
                    $('#successModal .btn-primary').attr('href', 'your_link_here'); // Set the link if needed

                    $('#importPricesModal').modal('hide');

                    // Show success modal
                    $('#successModal').modal('show');

                    // alert('Prices imported successfully!');
                    // console.log(response.details);
                    // $('#importPricesModal').modal('hide');
                    // Refresh the price data table
                    $('#price_data_table').DataTable().ajax.reload();
                } else {
                    // Display form errors
                    $.each(response.errors, function(fieldName, errorMessages) {
                        $('#error_' + fieldName).html(errorMessages.join('<br>'));
                    });
                    alert('Error updating prices: ' + response.message);
                }
            },
            error: function(xhr, status, error) {
                hideSpinner();
                alert('Error updating prices: ' + error);
            }
        });
    });

    // Toggle between securities and broker selection
    $('#id_securities, #id_broker').on('change', function() {
        var securitySelect = $('#id_securities');
        var brokerSelect = $('#id_broker');

        if ($(this).attr('id') === 'id_securities' && securitySelect.val().length > 0) {
            brokerSelect.prop('disabled', true);
        } else if ($(this).attr('id') === 'id_broker' && brokerSelect.val() !== '') {
            securitySelect.prop('disabled', true);
        } else {
            securitySelect.prop('disabled', false);
            brokerSelect.prop('disabled', false);
        }
    });

    // Toggle between date range and single date
    $('#id_start_date, #id_end_date, #id_single_date').on('change', function() {
        var startDate = $('#id_start_date');
        var endDate = $('#id_end_date');
        var singleDate = $('#id_single_date');
        var frequency = $('#id_frequency');

        if (singleDate.val()) {
            startDate.prop('disabled', true);
            endDate.prop('disabled', true);
            frequency.prop('disabled', true);
        } else if (startDate.val() || endDate.val()) {
            singleDate.prop('disabled', true);
        } else {
            startDate.prop('disabled', false);
            endDate.prop('disabled', false);
            singleDate.prop('disabled', false);
            frequency.prop('disabled', false);
        }
    });
});