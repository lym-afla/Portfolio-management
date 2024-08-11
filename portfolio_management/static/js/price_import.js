$(document).ready(function() {

    $('#import_prices').on('click', function() {
        $('#importPricesModal').modal('show');
    });

    $('#submitImportPrices').on('click', function() {
        var formData = new FormData($('#importPricesForm')[0]);

        $('#importPricesModal').modal('hide');

        $('#importProgressModal').modal('show');
        updateProgressBar(0);
        $('#importStatus').text('Initializing import...');

        var xhr = new XMLHttpRequest();
        xhr.open('POST', 'import_prices/', true);
        xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
        xhr.onprogress = function(e) {
            var lines = e.target.responseText.split('\n');
            lines.forEach(function(line) {
                if (line) {
                    try {
                        var data = JSON.parse(line);
                        if (data.status === 'progress' || data.status === 'error') {
                            updateProgressBar(data.progress);
                            $('#importStatus').text(data.status === 'progress' 
                                ? `Importing ${data.security_name} for date ${data.date} (${data.current}/${data.total})`
                                : `Error: ${data.message}`
                            );
                        } else if (data.status === 'success' || data.status === 'complete') {
                            console.log("Hiding progress modal");
                            setTimeout(function() {
                                $('#importProgressModal').modal('hide');
                                handleImportSuccess(data);
                            }, 100);
                        }
                    } catch (error) {
                        console.error('Error parsing JSON:', error);
                    }
                }
            });
        };
        xhr.onload = function() {
            if (xhr.status !== 200) {
                $('#importProgressModal').modal('hide');
                handleImportError('An error occurred during the import process.');
            }
        };
        xhr.onerror = function() {
            $('#importProgressModal').modal('hide');
            handleImportError('An error occurred during the import process.');
        };
        xhr.send(formData);
    });

    function updateProgressBar(progress) {
        progress = Math.round(progress);
        $('#importProgressBar').css('width', progress + '%')
                               .attr('aria-valuenow', progress)
                               .text(progress + '%');
    }

    function handleImportSuccess(response) {
        let resultsHtml = '<h4>Import results</h4>';

        // Add summary of import parameters
        resultsHtml += '<div class="alert alert-info">';
        resultsHtml += `<p><strong>Import Summary:</strong></p>`;
        resultsHtml += `<p>Date Range: ${response.start_date} to ${response.end_date}</p>`;
        resultsHtml += `<p>Frequency: ${response.frequency}</p>`;
        resultsHtml += `<p>Total Dates: ${response.total_dates}</p>`;
        resultsHtml += '</div>';

        // Table for successfully processed securities
        resultsHtml += '<h5>Processed Securities</h5>';
        resultsHtml += '<table class="table table-striped">';
        resultsHtml += '<thead><tr><th>Security</th><th>Updated Dates</th><th>Skipped Dates</th><th>Errors</th></tr></thead>';
        resultsHtml += '<tbody>';

        // Table for skipped securities
        let skippedSecuritiesHtml = '<h5>Skipped Securities</h5>';
        skippedSecuritiesHtml += '<table class="table table-striped">';
        skippedSecuritiesHtml += '<thead><tr><th>Security</th><th>Reason</th></tr></thead>';
        skippedSecuritiesHtml += '<tbody>';

        let hasProcessedSecurities = false;
        let hasSkippedSecurities = false;

        if (Array.isArray(response.details)) {
            response.details.forEach(function(detail) {
                if (detail.status === 'skipped') {
                    hasSkippedSecurities = true;
                    skippedSecuritiesHtml += '<tr>';
                    skippedSecuritiesHtml += `<td>${detail.security_name || 'N/A'}</td>`;
                    skippedSecuritiesHtml += `<td>${detail.message || 'Unknown reason'}</td>`;
                    skippedSecuritiesHtml += '</tr>';
                } else {
                    hasProcessedSecurities = true;
                    resultsHtml += '<tr>';
                    resultsHtml += `<td>${detail.security_name || 'N/A'}</td>`;
                    resultsHtml += `<td>${Array.isArray(detail.updated_dates) ? detail.updated_dates.length : 'N/A'}</td>`;
                    resultsHtml += `<td>${Array.isArray(detail.skipped_dates) ? detail.skipped_dates.length : 'N/A'}</td>`;
                    resultsHtml += `<td>${formatErrors(detail.errors)}</td>`;
                    resultsHtml += '</tr>';
                }
            });
        } else {
            resultsHtml += '<tr><td colspan="4">No details provided</td></tr>';
        }

        resultsHtml += '</tbody></table>';
        skippedSecuritiesHtml += '</tbody></table>';

        // Only add the processed securities table if there are any
        if (hasProcessedSecurities) {
            $('#successModal .modal-body').html(resultsHtml);
        } else {
            $('#successModal .modal-body').html('<p>No securities were processed.</p>');
        }

        // Add the skipped securities table if there are any
        if (hasSkippedSecurities) {
            $('#successModal .modal-body').append(skippedSecuritiesHtml);
        }

        $('#successModal .modal-title').text('Price Import Results');
        $('#successModal .modal-footer a.btn-primary').hide();
        $('#successModal').modal('show');
        
        $('#price_data_table').DataTable().ajax.reload();
    }

    function handleImportError(errorMessage) {
        $('#successModal .modal-body').html('<div class="alert alert-danger">' + errorMessage + '</div>');
        $('#successModal .modal-title').text('Import error');
        $('#successModal .modal-footer a.btn-primary').hide();
        $('#successModal').modal('show');
    }

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

    // Helper functions
    function formatDates(dates) {
        if (!Array.isArray(dates) || dates.length === 0) return 'None';
        return '<ul class="list-unstyled mb-0">' + 
               dates.map(date => `<li>• ${formatDate(date)}</li>`).join('') + 
               '</ul>';
    }
    
    function formatErrors(errors) {
        if (!Array.isArray(errors) || errors.length === 0) return 'None';
        return '<ul class="list-unstyled mb-0 text-danger">' + 
               errors.map(error => `<li>• ${error}</li>`).join('') + 
               '</ul>';
    }

    function formatDate(dateString) {
        if (!dateString) return 'Invalid date';
        const options = { year: 'numeric', month: 'short', day: 'numeric' };
        return new Date(dateString).toLocaleDateString(undefined, options);
    }
});