$(document).ready(function() {

    $('#closedTableYearSelector').on('change', function() {
        updateClosedPositionsTable();
    });

    function updateClosedPositionsTable() {
        const timespan = $('#closedTableYearSelector').val();
        $('#loadingIndicatorClosedTable').removeClass('d-none').addClass('d-flex');

        $.ajax({
            url: '/closed_positions/update_table/',
            method: 'POST',
            data: JSON.stringify({ timespan: timespan }),
            contentType: 'application/json',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            success: function(response) {
                if (response.ok) {

                    // Clear the existing data
                    if ($.fn.DataTable.isDataTable('#table-closed')) {
                        $('#table-closed').DataTable().clear().destroy();
                    }

                    // Update the table HTML
                    $('#table-closed tbody').html(response.tbody);
                    $('#table-closed tfoot').html(response.tfoot);

                    // Initialize or reinitialize DataTables
                    if ($.fn.DataTable.isDataTable('#table-closed')) {
                        $('#table-closed').DataTable().destroy();
                    }
                    $('#table-closed').DataTable({
                        searching: true,
                        paging: true,
                        pageLength: 25,
                        autoWidth: false,
                        ordering: false,
                        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
                        columnDefs: [
                            { orderable: false, targets: [0, 2, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18] }
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

                }
            },
            error: function(xhr, status, error) {
                console.error("An error occurred: " + error);
            },
            complete: function() {
                $('#loadingIndicatorClosedTable').removeClass('d-flex').addClass('d-none');
            }
        });
    }

    // Initial load
    updateClosedPositionsTable();

});