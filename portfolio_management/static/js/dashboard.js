$(document).ready(function () {

    $('#update-broker-performance-database').on('click', function() {
        $.ajax({
            url: "/database/update-broker-performance-database/",
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