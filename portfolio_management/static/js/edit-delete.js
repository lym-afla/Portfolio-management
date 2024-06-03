$(document).ready(function() {
    
    // Enable Edit and Delete buttons on radio button selection
    $('.edit-radio').change(function() {
        $('#editEntryButton').prop('disabled', false);
        $('#deleteEntryButton').prop('disabled', false);
    });

    // Edit Button Click
    $('#editEntryButton').click(function() {
        handleEditClick($(this).data('edit-type'));
    });

    // Delete Button Click
    $('#deleteEntryButton').click(function() {
        handleDeleteClick($(this).data('delete-type'));
    });

    // Confirm Delete Button Click
    $('#confirmDeleteButton').click(function() {
        confirmDelete($(this).data('delete-type'), $(this).data('item-id'));
    });
});

// Handle Edit Click
function handleEditClick(type) {
    var selectedRadio = $('.edit-radio:checked');
    if (selectedRadio.length) {
        var itemId = selectedRadio.val();
        $.ajax({
            url: `/database/edit_${type}/${itemId}/`,
            method: 'GET',
            success: function(data) {
                console.log(data.form_html);
                $(`#${type}FormModalContainer`).html(data.form_html);
                console.log((`#${type}FormModalContainer`));
                $(`#${type}FormModalContainer`).find('.modal').modal('show');
            }
        });
    }
}

// Handle Delete Click
function handleDeleteClick(type) {
    var selectedRadio = $('.edit-radio:checked');
    if (selectedRadio.length) {
        $('#confirmDeleteButton').data('type', type);
        $('#confirmDeleteButton').data('item-id', selectedRadio.val());
    }
}

// Confirm Delete
function confirmDelete(type, itemId) {
    $.ajax({
        url: `/database/delete_${type}/${itemId}/`,
        method: 'DELETE',
        headers: {
            'X-CSRFToken': $('[name=csrfmiddlewaretoken]').val()
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