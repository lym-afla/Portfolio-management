$(document).ready(function () {
    var formLoaded = {}; // Object to track which forms have been loaded

    // Function to load the form into the modal
    function loadForm(type) {
        var containerMap = {
            transaction: '#transactionFormModalContainer',
            broker: '#brokerFormModalContainer',
            price: '#priceFormModalContainer',
            security: '#securityFormModalContainer'
        };
        // var url = urlMap[type];
        var container = containerMap[type];

        if (!formLoaded[type]) {
            $.ajax({
                url: urls[type],
                method: 'GET',
                success: function (data) {
                    $(container).html(data.form_html); // Load form HTML into the container
                    $(container).find('form').attr('data-type', type); // Set the form's type
                    $(container).find('.modal').modal('show'); // Show the modal
                    attachFormSubmitHandler(type);
                    formLoaded[type] = true; // Mark form as loaded
                }
            });
        } else {
            $(container).find('.modal').modal('show');
        }
    }

    // Function to handle form submission
    function attachFormSubmitHandler(type) {
        var containerMap = {
            transaction: '#transactionFormModalContainer',
            broker: '#brokerFormModalContainer',
            price: '#priceFormModalContainer',
            security: '#securityFormModalContainer'
        };
        var container = containerMap[type];
        console.log(type);

        $(container).find('form').off('submit').on('submit', function (e) {
            e.preventDefault();
            var form = $(this);
            form.attr('action', urls[type]); // Set the form's action URL

            $.ajax({
                type: 'POST',
                url: urls[type],
                data: form.serialize(),
                success: function (response) {
                    // Check if the response contains a redirect URL
                    if (response.redirect_url) {
                        // If a redirect URL is provided, redirect the user
                        window.location.href = response.redirect_url;
                    } else {
                        // If no redirect URL is provided, close the modal or perform other actions
                        $(container).find('.modal').modal('hide');
                        location.reload();
                    }
                },
                error: function (xhr) {
                    var errors = xhr.responseJSON;
                    $.each(errors, function (field, messages) {
                        console.log(messages);
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

    // Event listeners for the buttons
    $('button[data-type]').on('click', function () {
        var type = $(this).data('type');
        loadForm(type);
    });
});
