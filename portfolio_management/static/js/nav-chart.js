document.addEventListener('DOMContentLoaded', function() {

    // Handle custom timeline
    const timelineForm = document.getElementById('chartCustomTimeline');
    timelineForm.addEventListener('submit', handleCustomTimeline);

    updateChart(NAVBarChart);

    // Handle breakdown change
    const breakdownForm = document.getElementById('selectChartBreakdown');
    breakdownForm.addEventListener('change', async function() {
        await updateChart(NAVBarChart);
    });

    const frequencyButtons = document.querySelectorAll('.chart-frequency');
    frequencyButtons.forEach(button => {
        button.addEventListener('click', async function() {
            await updateChart(NAVBarChart);
        });
    })
});

// Setting the chart
function pieChartInitialization(type, chartData) {

    const ctxChart = document.getElementById(`${type}PieChart`);

    // Create a new Chart instance
    window.myChart = new Chart(ctxChart, {
        type: 'pie',
        data: {
            labels: chartData.labels,
            datasets: chartData.datasets
        },
        plugins: [ChartDataLabels],
        options: {
            responsive: false,
            radius: '75%',
            layout: {
                padding: 45
            },
            plugins: {
                datalabels: {
                    anchor: 'end',
                    align: 'end',
                    formatter: (value, ctx) => {
                        let sum = 0;
                        let dataArr = ctx.chart.data.datasets[0].data;
                        dataArr.map(data => {
                            sum += Number(data);
                        });
                        let percentage = (Number(value) * 100 / sum).toFixed(0) + '%';
                        // Create array from string (each element of array shown on a new line)
                        label = ctx.chart.data.labels[ctx.dataIndex].split(' ');
                        // Add ':' to the end of the last word
                        label[label.length - 1] = label[label.length - 1] + ':';
                        // Add number
                        label.push(percentage);
                        return label;
                    },
                },
                legend: {
                    display: false,
                }
            },
        },
    });
}

async function updateChart(chart) {

    // Show loading indicator
    document.getElementById('loadingIndicatorNAVChart').style.display = 'flex';
    // document.getElementById('NAVBarChart').style.display = 'none';

    const frequency = document.querySelector('input[name="chartFrequency"]:checked').value;
    const from = document.getElementById("chartDateFrom").value;
    const to = document.getElementById("chartDateTo").value;
    const breakdown = document.getElementById("selectChartBreakdown").value;
    const chartData = await getNAVChartData(frequency, from, to, breakdown);

    // Hide loading indicator and show chart
    document.getElementById('loadingIndicatorNAVChart').style.display = 'none';
    // document.getElementById('NAVBarChart').style.display = 'block';

    chart.data.labels = chartData.labels;
    chart.data.datasets = chartData.datasets;
    chart.options.scales.y.title.text = chartData.currency;
    chart.update();
    // chart.draw();

}

// Handling changing the timeline of the chart. Function referenced directly in timeline-chart.html
function changeTimeline(element) {

    const toDate = new Date(document.getElementById('chartDateTo').value);
    let fromDate;

    switch (element.value) {
        case 'YTD':
            fromDate = new Date(new Date().getFullYear(), 0, 1);
            break;
        case '3m':
            fromDate = new Date(toDate.getFullYear(), toDate.getMonth() - 3, toDate.getDate());
            break;
        case '6m':
            fromDate = new Date(toDate.getFullYear(), toDate.getMonth() - 6, toDate.getDate());
            break;
        case '12m':
            fromDate = new Date(toDate.getFullYear(), toDate.getMonth() - 12, toDate.getDate());
            break;
        case '3Y':
            fromDate = new Date(toDate.getFullYear() - 3, toDate.getMonth(), toDate.getDate());
            break;
        case '5Y':
            fromDate = new Date(toDate.getFullYear() - 5, toDate.getMonth(), toDate.getDate());
            break;
        case 'All':
            fromDate = new Date('1900-01-01');
            break;
        case 'Custom':
            let myModal = new bootstrap.Modal(document.getElementById('modalChartTimeline'), {});
            myModal.show();
            return;
    }

    // Run if case is not 'Custom'
    document.getElementById('chartDateFrom').value = convertDate(fromDate);
    updateChart(NAVBarChart);
}

// Convert to YYYY-mmm-dd format
function convertDate(date) {
    let day = ("0" + date.getDate()).slice(-2);
    let month = ("0" + (date.getMonth() + 1)).slice(-2);
    return date.getFullYear()+"-"+(month)+"-"+(day);
}

// Fetching data for the chart. Defined in layout.js as used on the several pages
function getNAVChartData(frequency, from, to, breakdown) {

    return fetch(`/dashboard/get_nav_chart_data?frequency=${frequency}&from=${from}&to=${to}&breakdown=${breakdown}`)
        .then(response => response.json())
        .then(chartData => {
            return chartData;
        })
        .catch(error => {
            console.error('Error fetching chart data:', error);
            return null;
        });
}

// Handling click of custom timeline modal
function handleCustomTimeline(event) {
    event.preventDefault();

    // Close the Modal
    const modalReference = document.getElementById("modalChartTimeline");
    const timelineModal = bootstrap.Modal.getInstance(modalReference);
    timelineModal.hide();

    // Feed select element as second argument to recover target correctly
    updateChart(NAVBarChart);

}

// // Show actual chart settings
// function updateFrequencySetting(frequency) {
//     const chartFrequencySettings = document.querySelectorAll('.chart-frequency');               
//     for (let i = 0; i < chartFrequencySettings.length; i++) {
//         if (chartFrequencySettings[i].value === frequency) {
//             chartFrequencySettings[i].checked = true;
//             break;
//         }                
//     }
// }