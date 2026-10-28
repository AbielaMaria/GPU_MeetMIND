(function (global) {
    "use strict";

    var CLOSE_MS = 160;

    var uid = 0;

    function makeButton(label, variant) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "mm-dlg-btn mm-dlg-btn-" + variant;
        b.textContent = label;
        return b;
    }

    function open(opts, withCancel) {
        opts = opts || {};
        var dlg = document.createElement("dialog");

        if (typeof dlg.showModal !== "function") {
            if (withCancel) return Promise.resolve(window.confirm(opts.message || ""));
            window.alert(opts.message || "");
            return Promise.resolve();
        }

        return new Promise(function (resolve) {
            var previousFocus = document.activeElement;
            var id = "mm-dlg-" + (++uid);

            dlg.className = "mm-dlg";
            dlg.setAttribute("aria-labelledby", id + "-title");
            dlg.setAttribute("aria-describedby", id + "-desc");

            var title = document.createElement("h3");
            title.id = id + "-title";
            title.textContent = opts.title || (withCancel ? "Are you sure?" : "Notice");

            var message = document.createElement("p");
            message.id = id + "-desc";
            message.textContent = opts.message || "";

            var actions = document.createElement("div");
            actions.className = "mm-dlg-actions";

            var cancelBtn = null;
            if (withCancel) {
                cancelBtn = makeButton(opts.cancelText || "Cancel", "secondary");
                actions.appendChild(cancelBtn);
            }
            var okBtn = makeButton(
                opts.confirmText || opts.okText || (withCancel ? "Confirm" : "OK"),
                opts.danger ? "danger" : "primary"
            );
            actions.appendChild(okBtn);

            dlg.appendChild(title);
            dlg.appendChild(message);
            if (Array.isArray(opts.items) && opts.items.length) {
                dlg.classList.add("has-items");
                var list = document.createElement("ul");
                opts.items.forEach(function (text) {
                    var li = document.createElement("li");
                    li.textContent = text;
                    list.appendChild(li);
                });
                dlg.appendChild(list);
            }
            dlg.appendChild(actions);
            document.body.appendChild(dlg);

            var settled = false;
            function finish(result) {
                if (settled) return;
                settled = true;
                dlg.classList.remove("is-open");
                setTimeout(function () {
                    if (dlg.open) dlg.close();
                    dlg.remove();
                    if (previousFocus && typeof previousFocus.focus === "function") {
                        try { previousFocus.focus(); } catch (e) {}
                    }
                }, CLOSE_MS);
                resolve(withCancel ? result : undefined);
            }

            okBtn.addEventListener("click", function () { finish(true); });
            if (cancelBtn) cancelBtn.addEventListener("click", function () { finish(false); });

            dlg.addEventListener("keydown", function (e) {
                if (e.key === "Escape") {
                    e.preventDefault();
                    e.stopPropagation();
                    finish(false);
                }
            });
            dlg.addEventListener("cancel", function (e) {
                e.preventDefault();
                finish(false);
            });

            dlg.addEventListener("click", function (e) {
                if (e.target !== dlg) return;
                var r = dlg.getBoundingClientRect();
                var inside = e.clientX >= r.left && e.clientX <= r.right &&
                    e.clientY >= r.top && e.clientY <= r.bottom;
                if (!inside) finish(false);
            });

            dlg.showModal();
            (opts.danger && cancelBtn ? cancelBtn : okBtn).focus();
            requestAnimationFrame(function () { dlg.classList.add("is-open"); });
        });
    }

    global.MeetMindDialog = {
        confirm: function (opts) { return open(opts, true); },
        alert: function (opts) { return open(opts, false); }
    };

})(window);
