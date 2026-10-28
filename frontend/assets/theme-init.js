(function () {
    try {
        var s = localStorage.getItem("meetmind-theme");
        if (s === "light" || s === "dark") {
            document.documentElement.setAttribute("data-theme", s);
        }
    } catch (e) {}
})();
