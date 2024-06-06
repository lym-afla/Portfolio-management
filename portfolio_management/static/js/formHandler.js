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
        console.log(type, itemId)
        confirmDelete(type, itemId);
    });
});

// Function to load the form into the modal
function loadForm(type, itemId = null) {
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
            $(container).find('.modal').modal('show'); // Show the modal
            attachFormSubmitHandler(form);
        }
    });
}

// Function to handle form submission
function attachFormSubmitHandler(form) {
    var type = form.attr('data-type');
    var itemId = form.attr('data-item-id');
    var actionUrl = itemId ? `/database/edit_${type}/${itemId}/` : urls[type];

    form.off('submit').on('submit', function (e) {
        e.preventDefault();
        // var form = $(this);
        // form.attr('action', urls[type]); // Set the form's action URL

        $.ajax({
            type: 'POST',
            url: actionUrl,
            data: form.serialize(),
            headers: {
                'X-CSRFToken': getCookie('csrftoken') // Add CSRF token to headers
            },
            success: function (response) {
                // Check if the response contains a redirect URL
                if (response.redirect_url) {
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
                location.reload();
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