$(document).ready(function() {

    $('#openTableYearSelector').on('change', function() {
        updateOpenPositionsTable();
    });

    function updateOpenPositionsTable() {
        const timespan = $('#openTableYearSelector').val();
        $('#loadingIndicatorOpenTable').removeClass('d-none').addClass('d-flex');

        $.ajax({
            url: '/open_positions/update_table/',
            method: 'POST',
            data: JSON.stringify({ timespan: timespan }),
            contentType: 'application/json',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            success: function(response) {
                // Clear the existing DataTable if it exists
                if ($.fn.DataTable.isDataTable('#table-open')) {
                    $('#table-open').DataTable().destroy();
                }

                if (response.ok) {
                    // Update the table HTML
                    $('#table-open tbody').html(response.tbody);
                    $('#table-open tfoot').html(response.tfoot);
                    
                    // Reinitialize DataTables
                    $('#table-open').DataTable({
                        searching: true,
                        paging: true,
                        pageLength: 25,
                        autoWidth: false,
                        ordering: false,
                        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
                        columnDefs: [
                            { orderable: false, targets: '_all' }
                        ],
                        // Bootstrap styling
                        dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
                             '<"row"<"col-sm-12"tr>>' +
                             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
                        language: {
                            search: "_INPUT_",
                            searchPlaceholder: "Search records"
                        }
                    });
                    
                    updateCashBalances(response.cash_balances);

                } else {
                    // Handle the case when no open positions are found
                    $('#table-open tbody').html('<tr><td colspan="100%" class="text-center">' + response.message + '</td></tr>');
                    $('#table-open tfoot').empty();
                    updateCashBalances({});
                }
            },
            error: function(xhr, status, error) {
                console.error("An error occurred: " + error);
                // Clear the existing DataTable if it exists
                if ($.fn.DataTable.isDataTable('#table-open')) {
                    $('#table-open').DataTable().destroy();
                }
                $('#table-open tbody').html('<tr><td colspan="100%" class="text-center">An error occurred while fetching data.</td></tr>');
                $('#table-open tfoot').empty();
                updateCashBalances({});
            },
            complete: function() {
                $('#loadingIndicatorOpenTable').removeClass('d-flex').addClass('d-none');
            }
        });
    }

    function updateCashBalances(cashBalances) {
        const headerRow = $('#cashBalancesHeader');
        const bodyRow = $('#cashBalancesBody');
        headerRow.empty();
        bodyRow.empty();
        
        for (const [currency, balance] of Object.entries(cashBalances)) {
            headerRow.append(`<th>${currency}</th>`);
            bodyRow.append(`<td>${balance}</td>`);
        }
    }

    // Initial load
    updateOpenPositionsTable();

});