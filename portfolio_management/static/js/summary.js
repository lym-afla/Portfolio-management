$(document).ready(function() {
    // Initial update with YTD
    updateExposureTable('YTD');

    // Add event listener for the select element
    $('#exposureTableYear').on('change', function() {
        updateExposureTable($(this).val());
    });
});

async function updateExposureTable(timespan) {
    // Show loading indicator
    $('#loadingIndicatorExposureTable').addClass('show');

    try {
        const exposureTableData = await getExposureTable(timespan);
        // Clear existing table content
        const tableBody = $('#table-portfolio-breakdown tbody');
        tableBody.empty();

        categoriesName = {
            'consolidated_context': 'Consolidated',
            'unrestricted_context': 'Unrestricted',
            'restricted_context': 'Restricted'
        };
        console.log(categoriesName);

        // Populate table with new data
        ['consolidated_context', 'unrestricted_context', 'restricted_context'].forEach(category => {
            // Add category header
            tableBody.append(`<tr><td class="fixed-column fw-bold" colspan="14">${categoriesName[category]}</td></tr>`);

            // Add rows for each asset type
            exposureTableData[category].forEach(row => {
                if (row.name === 'TOTAL') {
                    total_row_class = 'fw-bold';
                } else {
                    total_row_class = '';
                }
                tableBody.append(`
                    <tr>
                        <td class="fixed-column ${total_row_class}">${row.name}</td>
                        <td class="text-center ${total_row_class}">${row.cost}</td>
                        <td class="text-center ${total_row_class}">${row.unrealized}</td>
                        <td class="text-center fst-italic ${total_row_class}">${row.unrealized_percent}</td>
                        <td class="text-center ${total_row_class}">${row.market_value}</td>
                        <td class="text-center fst-italic ${total_row_class}">${row.portfolio_percent}</td>
                        <td class="text-center ${total_row_class}">${row.realized}</td>
                        <td class="text-center fst-italic ${total_row_class}">${row.realized_percent}</td>
                        <td class="text-center ${total_row_class}">${row.capital_distribution}</td>
                        <td class="text-center fst-italic ${total_row_class}">${row.capital_distribution_percent}</td>
                        <td class="text-center ${total_row_class}">${row.commission}</td>
                        <td class="text-center fst-italic ${total_row_class}">${row.commission_percent}</td>
                        <td class="text-center fw-bold">${row.total}</td>
                        <td class="text-center fw-bold fst-italic">${row.total_percent}</td>
                    </tr>
                `);
            });
        });
    } catch (error) {
        console.error('Error updating exposure table:', error);
        $('#table-portfolio-breakdown tbody').html('<tr><td colspan="14">Error loading data. Please try again.</td></tr>');
    } finally {
        // Hide loading indicator
        $('#loadingIndicatorExposureTable').removeClass('show');
    }
}

async function getExposureTable(timespan) {
    
    try {
        const response = await fetch(`/summary/exposure-table?timespan=${timespan}`);
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const data = await response.json(); // Parse JSON once
        return data;
    } catch (error) {
        console.error('Error fetching exposure table:', error);
        throw error;
    }
}
