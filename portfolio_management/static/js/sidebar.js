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