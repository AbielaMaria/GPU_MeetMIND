(function () {
    var sp = new URLSearchParams(location.search).get("mode");
    var mode = (sp === "signup" || sp === "signin" || sp === "verify" || sp === "pending")
        ? sp
        : (location.pathname.indexOf("verify-otp") !== -1 ? "verify"
            : location.pathname.indexOf("account-pending") !== -1 ? "pending"
            : location.pathname.indexOf("sign-up") !== -1 ? "signup" : "signin");
    document.body.setAttribute("data-auth-mode", mode);
})();
