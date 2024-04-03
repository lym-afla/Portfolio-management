function changeTimeline(element, dateString) {

    // document.getElementById('chartDateTo').value = dateString;
    let toDate = new Date(dateString);

    switch (element.value) {
        case 'YTD':
            let YTD = new Date(new Date().getFullYear(), 0, 1);
            document.getElementById('chartDateFrom').value = convertDate(YTD);
            break;
        case '3m':
            let threeM = new Date(toDate.getFullYear(), toDate.getMonth() - 3, toDate.getDate());
            document.getElementById('chartDateFrom').value = convertDate(threeM);
            console.log(convertDate(threeM));
            break;
        case '6m':
            let sixM = new Date(toDate.getFullYear(), toDate.getMonth() - 6, toDate.getDate());
            document.getElementById('chartDateFrom').value = convertDate(sixM);
            console.log(convertDate(sixM));
            break;
        case '12m':
            let twelveM = new Date(toDate.getFullYear(), toDate.getMonth() - 12, toDate.getDate());
            document.getElementById('chartDateFrom').value = convertDate(twelveM);
            console.log(convertDate(twelveM));
            break;
        case '3Y':
            let threeY = new Date(toDate.getFullYear() - 3, toDate.getMonth(), toDate.getDate());
            document.getElementById('chartDateFrom').value = convertDate(threeY);
            console.log(convertDate(threeY));
            break;
        case '5Y':
            let fiveY = new Date(toDate.getFullYear() - 5, toDate.getMonth(), toDate.getDate());
            document.getElementById('chartDateFrom').value = convertDate(fiveY);
            console.log(convertDate(fiveY));
            break;
        case 'All':
            fromDate = new Date('2000-01-01');
            let all = new Date(fromDate.getFullYear(), fromDate.getMonth(), fromDate.getDate());
            document.getElementById('chartDateFrom').value = convertDate(all);
            console.log(convertDate(all));
            break;
        case 'Custom':
            let myModal = new bootstrap.Modal(document.getElementById('modalChartTimeline'), {});
            // $('#modalChartTimeline').modal("show")
            myModal.show();
            break;
    }
}

// Convert to YYY-mmm-dd format
function convertDate(date) {
    let day = ("0" + date.getDate()).slice(-2);
    let month = ("0" + (date.getMonth() + 1)).slice(-2);
    return date.getFullYear()+"-"+(month)+"-"+(day);
}