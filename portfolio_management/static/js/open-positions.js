$(document).ready(function() {

    // Initialize the table
    const openPositionsTable = $('#table-open').DataTable( {
        searching: true,
        paging: true,
        pageLength: 25,
        autoWidth: false,
        ordering: false,
        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
        columnDefs: [
            { orderable: false}
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

    $('#openTableYearSelector').on('change', function() {
        updateOpenPositionsTable();
    });

    function updateOpenPositionsTable() {
        const timespan = $('#openTableYearSelector').val();
        $('#loadingIndicatorOpenTable').removeClass('d-none').addClass('d-flex');

        $.ajax({
            url: '/open-positions/update_table/',
            method: 'POST',
            data: JSON.stringify({ timespan: timespan }),
            contentType: 'application/json',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            success: function(response) {
                if (response.ok) {
                    openPositionsTable.clear();
                    $('#table-open tbody').html(response.tbody);
                    $('#table-open tfoot').html(response.tfoot);
                    console.log(response.tbody);
                    // openPositionsTable.rows.add($(response.tbody)).draw();
                    updateCashBalances(response.cash_balances);
                }
            },
            error: function(xhr, status, error) {
                console.error("An error occurred: " + error);
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

    // updateCashBalances();
    // updateOpenPositionsTable();

    // // Year selector change event
    // $('#openTableYearSelector').change(function() {
    //     updateCashBalances();
    //     updateOpenPositionsTable();
    // });



// async function updateOpenPositionsTable(timespan) {
//     // Show loading indicator
//     $('#loadingIndicatorOpenTable').addClass('show');

//     try {
//         const OpenTableData = await getOpenTableData(timespan);
//         // Clear existing table content
//         const tableBody = $('#table-open tbody');
//         tableBody.empty();

//         // Add new data
//         OpenTableData.forEach(row => {
//             openPositionsTable.row.add([
//                 row.type,
//                 row.name,
//                 row.currency,
//                 row.current_position,
//                 row.investment_date,
//                 row.entry_price,
//                 row.entry_value,
//                 '',  // Empty column
//                 row.current_price,
//                 row.current_value,
//                 row.share_of_portfolio,
//                 row.realized_gl,
//                 row.unrealized_gl,
//                 row.price_change_percentage,
//                 '',  // Empty column
//                 row.capital_distribution,
//                 row.capital_distribution_percentage,
//                 '',  // Empty column
//                 row.commission,
//                 row.commission_percentage,
//                 '',  // Empty column
//                 row.total_return_amount,
//                 row.total_return_percentage,
//                 row.irr
//             ]);
//         });

//         // Update totals in the footer
//         updateTableFooter(response.totals);

//     function updateOpenPositionsTable() {
//         const selectedYear = $('#openTableYearSelector').val();
//         // const selectedBroker = $('#brokerSelect').val();
//         $('#loadingIndicatorOpenTable').addClass('show');
        
//         $.ajax({
//             url: '/open-positions/update_table/',
//             type: 'POST',
//             headers: {
//                 'X-CSRFToken': getCookie('csrftoken')
//             },
//             contentType: 'application/json',
//             data: JSON.stringify({ 
//                 timespan: selectedYear,
//                 // broker_id: selectedBroker
//             }),
//             success: function(response) {
//                 if (response.ok) {
//                     // Clear existing table data
//                     openPositionsTable.clear();

//                     // Add new data
//                     response.data.forEach(function(row) {
//                         openPositionsTable.row.add([
//                             row.type,
//                             row.name,
//                             row.currency,
//                             row.current_position,
//                             row.investment_date,
//                             row.entry_price,
//                             row.entry_value,
//                             '',  // Empty column
//                             row.current_price,
//                             row.current_value,
//                             row.share_of_portfolio,
//                             row.realized_gl,
//                             row.unrealized_gl,
//                             row.price_change_percentage,
//                             '',  // Empty column
//                             row.capital_distribution,
//                             row.capital_distribution_percentage,
//                             '',  // Empty column
//                             row.commission,
//                             row.commission_percentage,
//                             '',  // Empty column
//                             row.total_return_amount,
//                             row.total_return_percentage,
//                             row.irr
//                         ]);
//                     });

//                     // Update totals in the footer
//                     updateTableFooter(response.totals);

//                     // Redraw the table
//                     openPositionsTable.draw();
//                     $('#loadingIndicatorOpenTable').removeClass('show');
//                 } else {
//                     console.error('Failed to update open positions table');
//                     $('#loadingIndicatorOpenTable').removeClass('show');
//                 }
//             },
//             error: function(error) {
//                 console.error('Error updating open positions table:', error);
//                 $('#loadingIndicatorOpenTable').removeClass('show');
//             }
//         });
//     }

//     function updateTableFooter(totals) {
//         const footer = $('#table-open tfoot tr');
//         footer.find('td:eq(6)').text(totals.entry_value);
//         footer.find('td:eq(9)').text(totals.current_value);
//         footer.find('td:eq(11)').text(totals.realized_gl);
//         footer.find('td:eq(12)').text(totals.unrealized_gl);
//         footer.find('td:eq(13)').text(totals.price_change_percentage);
//         footer.find('td:eq(15)').text(totals.capital_distribution);
//         footer.find('td:eq(16)').text(totals.capital_distribution_percentage);
//         footer.find('td:eq(18)').text(totals.commission);
//         footer.find('td:eq(19)').text(totals.commission_percentage);
//         footer.find('td:eq(21)').text(totals.total_return_amount);
//         footer.find('td:eq(22)').text(totals.total_return_percentage);
//         // Update IRR if available
//         if (totals.irr) {
//             footer.find('td:eq(23)').text(totals.irr);
//         }
//     }
// });

// function updateCashBalances() {
//     const selectedYear = $('#openTableYearSelector').val();
    
//     $.ajax({
//         url: '/open-positions/get_cash_balances/',
//         type: 'POST',
//         headers: {
//             'X-CSRFToken': getCookie('csrftoken')
//         },
//         contentType: 'application/json',
//         data: JSON.stringify({timespan: selectedYear}),
//         success: function(response) {
//             if (response.ok) {
//                 displayCashBalances(response.cash_balances);
//             } else {
//                 console.error('Failed to fetch cash balances');
//             }
//         },
//         error: function(error) {
//             console.error('Error fetching cash balances:', error);
//         }
//     });
// }

// function displayCashBalances(cashBalances) {
//     let tableHtml = '<table class="table table-sm"><thead><tr><th>Currency</th><th>Balance</th></tr></thead><tbody>';
    
//     for (const [currency, balance] of Object.entries(cashBalances)) {
//         tableHtml += `<tr><td>${currency}</td><td>${balance}</td></tr>`;
//     }
    
//     tableHtml += '</tbody></table>';
    
//     $('.col-3:eq(1)').html('<h6 class="form-label">Cash balance</h6>' + tableHtml);
// }