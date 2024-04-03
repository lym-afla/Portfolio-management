function fillCurrency_old(id) {
    let asset = document.getElementById(id).value
    
    let table = document.getElementsByTagName("table")[0]
    let tbody = table.getElementsByTagName("tbody")[0]
    let rows = tbody.getElementsByTagName("tr")

    for (let i = 0; i < rows.length; i++) {
        if (asset == rows[i].getElementsByTagName("td")[1].innerHTML) {
            document.getElementById("inputTransactionCur").value = rows[i].getElementsByTagName("td")[3].innerHTML
        }
    }
}

function fillTransactionForm(element) {
    let name = element.closest("tr").getElementsByTagName("td")[1].innerHTML;
    let type = element.innerHTML.trim();
    let currency = element.closest("tr").getElementsByTagName("td")[2].innerHTML;

    // document.getElementById("inputTransactionName").value = name;
    document.getElementById("inputTransactionTypeTransaction").value = type;
    document.getElementById("inputTransactionCur").value = currency;

    let selectElement = document.getElementById("inputTransactionName");

    let optionElement = document.createElement("option");
    optionElement.value = name;
    optionElement.innerHTML = name;
    selectElement.appendChild(optionElement);
    selectElement.value = name;
    
}