$(document).ready(function () {

    // Event listeners for the buttons
    $('button[data-type]').on('click', function () {
        var type = $(this).data('type');
        loadForm(type);
    });

    // Enable Edit and Delete buttons on radio button selection
    $('.edit-radio').change(function() {
        $('#editEntryButton').prop('disabled', false);
        $('#deleteEntryButton').prop('disabled', false);
    });

    // Edit Button Click
    $('#editEntryButton').click(function() {
        var type = $(this).data('edit-type');
        handleEditClick(type);
    });

    // Delete Button Click
    $('#deleteEntryButton').click(function() {
        var type = $(this).data('delete-type');
        handleDeleteClick(type);
    });

    // Confirm Delete Button Click
    $('#confirmDeleteButton').click(function() {
        var type = $(this).data('delete-type');
        var itemId = $(this).data('item-id');
        confirmDelete(type, itemId);
    });

    // Import transactions click
    $('#importTransactionsBtn').on('click', function() {
        $.ajax({
            url: urls["import_form"],
            method: 'GET',
            headers: {
              'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(data) {
                $('#broker').empty();
                $.each(data.brokers, function(index, broker) {
                    $('#broker').append(`<option value="${broker.id}">${broker.name}</option>`);
                });
        
                $('#currency').empty();
                $.each(data.CURRENCY_CHOICES, function(index, currency) {
                    $('#currency').append(`<option value="${currency[0]}">${currency[1]}</option>`);
                });
        
                $('#importModal').modal('show');
                var form = $('#importModal').find('form');
                attachImportHandler(form);
            }
        });
    });
});

// Function to load the form into the modal
function loadForm(type, itemId = null, element = null) {
    var containerMap = {
        transaction: '#transactionFormModalContainer',
        broker: '#brokerFormModalContainer',
        price: '#priceFormModalContainer',
        security: '#securityFormModalContainer'
    };
    var url = itemId ? `/database/edit_${type}/${itemId}/` : urls[type];
    var container = containerMap[type];

    $.ajax({
        url: url,
        method: 'GET',
        success: function (data) {
            $(container).html(data.form_html); // Load form HTML into the container
            var form = $(container).find('form');
            form.attr('data-type', type); // Set the form's type
            form.attr('data-item-id', itemId); // Set the form's item ID if editing
            
            // Set pre-filled data
            if (element) {
                form.attr('data-importing', 'True');
                if (type === 'security') {
                    form.find('#id_name').val(element.name);
                    form.find('#id_isin').val(element.isin);
                    form.find('#id_currency').val(element.currency);
                } else if (type === 'transaction') {
                    console.log(element.date, element.type, element);
                    form.find('#id_date').val(element.date);
                    form.find('#id_price').val(element.price);
                    form.find('#id_type').val(element.type);
                    form.find('#id_currency').val(element.currency);
                    form.find('#id_quantity').val(element.quantity);
                    form.find('#id_cash_flow').val(element.dividend);
                    form.find('#id_commission').val(element.commission);

                    // Find the option element with the matching security name and update its text
                    var securitySelect = form.find('#id_security');
                    var option = securitySelect.find('option').filter(function() {
                        return $(this).text() === element.security_name;
                    });
                    option.prop('selected', true);
                }
            }
            
            $(container).find('.modal').modal('show'); // Show the modal
            attachFormSubmitHandler(form);
        }
    });
}

// Function to handle form submission
function attachFormSubmitHandler(form) {
    form.off('submit').on('submit', function (e) {
        e.preventDefault();
        var type = form.attr('data-type');
        var itemId = form.attr('data-item-id');
        var actionUrl = itemId ? `/database/edit_${type}/${itemId}/` : urls[type];

        // Serialize the form data
        var formData = form.serializeArray();

        // Add additional variable to form data if importing
        if (form.attr('data-importing') === 'True') {
            formData.push({ name: 'importing', value: true });
        }

        $.ajax({
            type: 'POST',
            url: actionUrl,
            data: $.param(formData),  // Serialize form data
            headers: {
                'X-CSRFToken': getCookie('csrftoken') // Add CSRF token to headers
            },
            success: function (response) {
                if (response.status === 'import_success') {
                    console.log("Import Success");
                    form.closest('.modal').modal('hide');
                    $('#importForm').trigger('submit'); // Continue importing
                } else if (response.redirect_url) { // Check if the response contains a redirect URL
                    // If a redirect URL is provided, redirect the user
                    window.location.href = response.redirect_url;
                } else {
                    // If no redirect URL is provided, close the modal or perform other actions
                    form.closest('.modal').modal('hide');
                    location.reload();
                }
            },
            error: function (xhr) {
                var errors = xhr.responseJSON;
                $.each(errors, function (field, messages) {
                    $.each(messages, function (index, message) {
                        var errorHtml = '<ul><li>' + message + '</li></ul>';
                        var errorContainer = $('#id_' + index + '_error');
                        errorContainer.html(errorHtml);
                        errorContainer.show();
                    });
                });
            }
        });
    });
}

// Handle Edit Click
function handleEditClick(type) {
    var selectedRadio = $('.edit-radio:checked');
    if (selectedRadio.length) {
        var itemId = selectedRadio.val();
        loadForm(type, itemId);
    }
}

// Handle Delete Click
function handleDeleteClick(type) {
    var selectedRadio = $('.edit-radio:checked');
    if (selectedRadio.length) {
        $('#confirmDeleteButton').data('delete-type', type);
        $('#confirmDeleteButton').data('item-id', selectedRadio.val());
    }
}

// Confirm Delete
function confirmDelete(type, itemId) {
    $.ajax({
        url: `/database/delete_${type}/${itemId}/`,
        method: 'DELETE',
        headers: {
            'X-CSRFToken': getCookie('csrftoken') // Add CSRF token to headers
        },
        success: function(response) {
            if (response.success) {
                window.location.reload();
            } else {
                alert('Failed to delete item.');
            }
        }
    });
}

// Function to get CSRF token from cookie
function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function attachImportHandler(form) {
    form.off('submit').on('submit', function (e) {
        e.preventDefault();

        const formData = new FormData(this);

        $.ajax({
            url: urls["import_transactions"],
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken') // Add CSRF token to headers
            },
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                form.closest('.modal').modal('hide');
                if (response.status === 'missing_security') {
                    // Pre-fill and open the security form
                    loadForm('security', null, response.security);
                } else if (response.status === 'success') {
                    transactions = response.transactions;
                    processTransactions(transactions, response.confirm_each);  // Assuming confirm_each is true
                }
            },
            error: function (xhr) {
                var errors = xhr.responseJSON.errors;
                console.log(errors);
            }
        });
  });
}

function processTransactions(transactions, confirm_each) {

    let currentTransactionIndex = 0;

    function showTransactionModal(transaction, confirm_each = false) {
        console.log("Show Transaction Modal. Before hiding modal", confirm_each);
        // $('#confirmationModal').modal('hide');
        console.log("Show Transaction Modal. After hiding modal");
        if (confirm_each) {
            console.log("Show Transaction Modal. Confirm_each is true");
            var details = `
                <table class="table">
                    <tr><th>Security Name</th><td>${transaction.security_name}</td></tr>
                    <tr><th>ISIN</th><td>${transaction.isin}</td></tr>
                    <tr><th>Date</th><td>${transaction.date}</td></tr>
                    <tr><th>Type</th><td>${transaction.type}</td></tr>
                    <tr><th>Currency</th><td>${transaction.currency}</td></tr>
                    <tr><th>Price</th><td>${transaction.price}</td></tr>
                    <tr><th>Quantity</th><td>${transaction.quantity}</td></tr>
                    <tr><th>Dividend</th><td>${transaction.dividend}</td></tr>
                    <tr><th>Commission</th><td>${transaction.commission}</td></tr>
                </table>
            `;
            $('#transactionDetails').html(details);
            $('#confirmationModal').modal('show');

            $('#confirmBtn').off('click').on('click', function() {
                processTransactionAction('confirm', confirm_each);
            });
            $('#skipBtn').off('click').on('click', function() {
                processTransactionAction('skip', confirm_each);
            });
            $('#editBtn').off('click').on('click', function() {
                loadForm('transaction', null, transaction);
            });
            $('#stopBtn').off('click').on('click', function() {
                processTransactionAction('stop');
            });
        } else {
            processTransactionAction('confirm', confirm_each);
        }
    }

    function processTransactionAction(action, confirm_each) {
        console.log(action);
        if (action === 'skip'){
            currentTransactionIndex++;
            console.log('Skipping transaction', confirm_each, currentTransactionIndex, transactions.length);
            if (currentTransactionIndex < transactions.length) {
                console.log('Next transaction after skipping', transactions[currentTransactionIndex]);
                showTransactionModal(transactions[currentTransactionIndex], confirm_each);
            } else {
                $('#confirmationModal').modal('hide');
                alert('All transactions processed');
                window.location.reload();
            }
            return;
        } else if (action === 'stop') {
            $('#confirmationModal').modal('hide');
            alert('Import process stopped');
            return
        } else if (action === 'confirm') {
        
            var transaction = transactions[currentTransactionIndex];
            console.log(transaction);

            var formData = new FormData();

            for (var key in transaction) {
                // Convert null or undefined values to empty strings
                formData.append(key, transaction[key] != null ? transaction[key] : '');
            }
    

            $.ajax({
                type: 'POST',
                url: urls['process_import_transactions'],
                headers: {
                    'X-CSRFToken': getCookie('csrftoken') // Add CSRF token to headers
                },
                data: formData,
                processData: false,
                contentType: false,
                success: function (response) {
                    if (response.status === 'success') {
                        currentTransactionIndex++;
                        if (currentTransactionIndex < transactions.length) {
                            showTransactionModal(transactions[currentTransactionIndex]);
                        } else {
                            $('#confirmationModal').modal('hide');
                            alert('All transactions processed');
                            window.location.reload();
                        }
                    } else if (response.status === 'check_required') {
                        loadForm('transaction', itemId=null, transaction);
                    } else if (response.status === 'error') {
                        showErrors(response.errors);
                    } 
                },
                error: function (xhr) {
                    var errors = xhr.responseJSON.errors;
                    showErrors(errors);
                }
            });
        }
    }

    showTransactionModal(transactions[currentTransactionIndex], confirm_each);
}

function showErrors(errors) {
    var errorContainer = $('#import-form-errors');
    errorContainer.empty();  // Clear previous errors

    // Create a Bootstrap alert div to contain the errors
    var alertDiv = $('<div class="alert alert-danger" role="alert"></div>');

    $.each(errors, function (field, messages) {
        var errorHtml = '<div><strong>' + field + ':</strong><ul>';
        $.each(messages, function (index, message) {
            errorHtml += '<li>' + message + '</li>';
        });
        errorHtml += '</ul></div>';
        alertDiv.append(errorHtml);
    });

    errorContainer.append(alertDiv);
    errorContainer.show();
}