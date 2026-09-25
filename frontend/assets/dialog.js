/* ============================================================
   MeetMind — themed confirm / alert dialogs
   ============================================================
   Drop-in replacement for window.confirm() / window.alert(), styled
   to match the "Start a new meeting?" modal in index.html. Colors,
   radii and shadows come from the page's own design tokens
   (theme.css, or index.html's :root), so light/dark theming follows
   the page automatically.

   Built on <dialog>.showModal() so it sits in the browser's top
   layer — above the admin page's own <dialog>s and the history
   drawer — and the rest of the page is inert while it's open.

     MeetMindDialog.confirm({ title, message, confirmText, cancelText, danger })
         -> Promise<boolean>
     MeetMindDialog.alert({ title, message, okText })
         -> Promise<void>
============================================================ */

(function (global) {
    "use strict";

    var STYLE_ID = "mm-dlg-style";
    var CLOSE_MS = 160;

    var CSS =
        ".mm-dlg{margin:auto;padding:24px;width:calc(100% - 40px);max-width:380px;" +
            "background:var(--bg-elevated);color:var(--text-primary);" +
            "border:1px solid var(--border);border-radius:var(--r-lg);" +
            "box-shadow:var(--shadow-lg);font-family:inherit;" +
            "opacity:0;transform:translateY(10px) scale(.96);" +
            "transition:transform .22s cubic-bezier(.16,1,.3,1),opacity .18s ease}" +
        ".mm-dlg.is-open{opacity:1;transform:none}" +
        ".mm-dlg::backdrop{background:rgba(15,15,20,.5)}" +
        ".mm-dlg h3{margin:0 0 10px;font-size:1.05rem;font-weight:650;" +
            "letter-spacing:-0.01em;color:var(--text-primary)}" +
        ".mm-dlg p{margin:0 0 22px;font-size:13px;line-height:1.55;" +
            "color:var(--text-secondary);overflow-wrap:anywhere}" +
        ".mm-dlg-actions{display:flex;justify-content:flex-end;gap:10px}" +
        ".mm-dlg-btn{font-family:inherit;font-size:13px;font-weight:600;letter-spacing:-0.005em;" +
            "padding:9px 15px;border-radius:var(--r-md);border:1px solid var(--accent);" +
            "box-shadow:var(--shadow-sm);cursor:pointer;display:inline-flex;" +
            "align-items:center;justify-content:center;" +
            "transition:background-color .16s ease,border-color .16s ease,color .16s ease,transform .09s ease}" +
        /* index.html gives every <button> a masked icon via ::before */
        ".mm-dlg-btn::before{content:none;display:none}" +
        ".mm-dlg-btn:active{transform:scale(.97)}" +
        ".mm-dlg-btn-secondary{background:var(--bg-surface);color:var(--accent)}" +
        ".mm-dlg-btn-secondary:hover{background:var(--accent-soft);border-color:var(--accent)}" +
        ".mm-dlg-btn-primary{background:var(--accent);color:#fff}" +
        ".mm-dlg-btn-primary:hover{background:var(--accent-hover);border-color:var(--accent-hover)}" +
        ".mm-dlg-btn-danger{background:var(--danger);border-color:var(--danger);color:#fff}" +
        ".mm-dlg-btn-danger:hover{background:var(--danger-hover);border-color:var(--danger-hover)}" +
        "@media (prefers-reduced-motion:reduce){.mm-dlg{transition:none}}";

    var uid = 0;

    function ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        var style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = CSS;
        document.head.appendChild(style);
    }

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
            // Very old browser without <dialog>: native is better than nothing.
            if (withCancel) return Promise.resolve(window.confirm(opts.message || ""));
            window.alert(opts.message || "");
            return Promise.resolve();
        }

        ensureStyle();

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

            // Handle Escape here and stop it, so page-level Escape handlers
            // (e.g. the history drawer) don't also react underneath.
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

            // A click on the backdrop targets the <dialog> itself but lands
            // outside its box; clicks in the card's padding land inside.
            dlg.addEventListener("click", function (e) {
                if (e.target !== dlg) return;
                var r = dlg.getBoundingClientRect();
                var inside = e.clientX >= r.left && e.clientX <= r.right &&
                    e.clientY >= r.top && e.clientY <= r.bottom;
                if (!inside) finish(false);
            });

            dlg.showModal();
            // Destructive confirms default to Cancel so Enter can't delete by accident.
            (opts.danger && cancelBtn ? cancelBtn : okBtn).focus();
            requestAnimationFrame(function () { dlg.classList.add("is-open"); });
        });
    }

    global.MeetMindDialog = {
        confirm: function (opts) { return open(opts, true); },
        alert: function (opts) { return open(opts, false); }
    };

})(window);
