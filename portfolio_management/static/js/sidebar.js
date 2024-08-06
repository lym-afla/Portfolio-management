function actionNav() {
    let sidebar = document.getElementsByClassName("extended_sidebar")[0];

    if (sidebar.style.width == "0px" || sidebar.style.width == "") {
        sidebar.style.paddingRight = "1rem";
        sidebar.style.width = "150px";
    }
    else {
        sidebar.style.paddingRight = "0";
        sidebar.style.width = "0px";
    }
}

function toggleSidebar() {
    document.getElementById('extendedSidebar').style.display = 'none';
}

function toggleExtendedSidebar() {
    var extendedSidebar = document.getElementById('extendedSidebar');
    if (extendedSidebar.style.width == "0px" || extendedSidebar.style.width == "") {
        extendedSidebar.style.paddingRight = "1rem";
        extendedSidebar.style.width = "150px";
        toggleDatabaseSubMenu();
    }
    else {
        extendedSidebar.style.paddingRight = "0";
        extendedSidebar.style.width = "0px";
    }
}

function toggleDatabaseSubMenu() {
    var subMenu = document.getElementById('databaseSubMenu');
    if (subMenu.style.display === 'none' || subMenu.style.display === '') {
        subMenu.style.display = 'block';
    } else {
        subMenu.style.display = 'none';
    }
}

// Function to get CSRF token from cookie. Here, since it is loaded with layout.html
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

// Spinner functions
function showSpinner() {
    $('#loadingOverlay').addClass('show');
}

function hideSpinner() {
    $('#loadingOverlay').removeClass('show');
}