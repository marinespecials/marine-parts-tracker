/* Marine Specials — small page behaviours. No framework needed. */
(function () {
    'use strict';
    var root = document.documentElement;

    // ---- Theme (initial value is set inline in <head> to avoid a flash) ----
    function setTheme(theme) {
        root.setAttribute('data-theme', theme);
        try { localStorage.setItem('ms-theme', theme); } catch (e) { /* private mode */ }
        document.dispatchEvent(new CustomEvent('themechange', { detail: theme }));
    }
    document.addEventListener('click', function (e) {
        var t = e.target.closest('[data-theme-toggle]');
        if (t) setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });

    // ---- Mobile navigation ----
    document.addEventListener('click', function (e) {
        if (e.target.closest('[data-nav-toggle]')) document.body.classList.toggle('nav-open');
        if (e.target.closest('.backdrop')) document.body.classList.remove('nav-open');
    });

    // ---- Close open dropdowns when clicking elsewhere ----
    document.addEventListener('click', function (e) {
        document.querySelectorAll('details.dropdown[open]').forEach(function (d) {
            if (!d.contains(e.target)) d.removeAttribute('open');
        });
    });

    // ---- Keyboard: "/" focuses search, Esc closes menus ----
    document.addEventListener('keydown', function (e) {
        var tag = (document.activeElement && document.activeElement.tagName) || '';
        if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(tag)) {
            var s = document.getElementById('global-search');
            if (s) { e.preventDefault(); s.focus(); s.select(); }
        }
        if (e.key === 'Escape') {
            document.body.classList.remove('nav-open');
            document.querySelectorAll('details.dropdown[open]').forEach(function (d) { d.removeAttribute('open'); });
        }
    });

    // ---- Confirm dangerous actions: <form data-confirm="..."> ----
    document.addEventListener('submit', function (e) {
        var f = e.target;
        var msg = f.getAttribute('data-confirm') || (e.submitter && e.submitter.getAttribute('data-confirm'));
        if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
        // stop double-submits (they would double-deduct stock)
        if (f.dataset.submitting) { e.preventDefault(); return; }
        if ((f.method || '').toLowerCase() === 'post') {
            f.dataset.submitting = '1';
            setTimeout(function () { delete f.dataset.submitting; }, 4000);
        }
    }, true);

    // ---- Auto-submit selects: <select data-autosubmit> ----
    document.addEventListener('change', function (e) {
        if (e.target.matches('select[data-autosubmit]')) e.target.form.requestSubmit ? e.target.form.requestSubmit() : e.target.form.submit();
    });

    // ---- Whole table rows clickable: <tr data-href="..."> ----
    document.addEventListener('click', function (e) {
        var row = e.target.closest('tr[data-href]');
        if (!row || e.target.closest('a, button, input, select, textarea, form, summary, details')) return;
        if (e.metaKey || e.ctrlKey) window.open(row.dataset.href, '_blank');
        else window.location = row.dataset.href;
    });

    // ---- Part pickers: fill every <select data-parts> from one JSON list ----
    // (keeps pages small — the parts list is sent once instead of once per row)
    var partsData = document.getElementById('parts-data');
    if (partsData) {
        var parts = JSON.parse(partsData.textContent);
        document.querySelectorAll('select[data-parts]').forEach(function (sel) {
            var mode = sel.getAttribute('data-parts');
            var frag = document.createDocumentFragment();
            parts.forEach(function (p) {
                var o = document.createElement('option');
                o.value = p.id;
                var label = p.name + (p.code ? ' (' + p.code + ')' : '');
                if (mode === 'price') label += ' · €' + p.cost + ' · ' + p.qty + ' in stock';
                else if (mode === 'stock') label += ' · ' + p.qty + ' in stock';
                o.textContent = label;
                o.dataset.cost = p.cost;
                frag.appendChild(o);
            });
            sel.appendChild(frag);
            // pre-fill the price box with the part's cost when a part is picked
            var priceInput = sel.form && sel.form.querySelector('[data-price-target]');
            if (priceInput) sel.addEventListener('change', function () {
                var opt = sel.options[sel.selectedIndex];
                if (opt && opt.dataset.cost && !priceInput.dataset.touched) priceInput.value = opt.dataset.cost;
            });
            if (priceInput) priceInput.addEventListener('input', function () { priceInput.dataset.touched = '1'; });
        });
    }

    // ---- Notes saved on this device: <textarea data-local-notes="key"> ----
    document.querySelectorAll('textarea[data-local-notes]').forEach(function (ta) {
        var key = 'ms-notes-' + ta.getAttribute('data-local-notes');
        try { ta.value = localStorage.getItem(key) || ''; } catch (e) { }
        var status = document.querySelector('[data-notes-status="' + ta.getAttribute('data-local-notes') + '"]');
        var timer;
        ta.addEventListener('input', function () {
            clearTimeout(timer);
            timer = setTimeout(function () {
                try { localStorage.setItem(key, ta.value); if (status) status.textContent = 'Saved on this device'; } catch (e) { }
            }, 400);
        });
    });

    // ---- Copy buttons: <button data-copy="#elementId"> ----
    document.addEventListener('click', function (e) {
        var b = e.target.closest('[data-copy]');
        if (!b) return;
        var el = document.querySelector(b.getAttribute('data-copy'));
        if (!el) return;
        var text = el.value !== undefined ? el.value : el.textContent;
        var done = function () { var old = b.innerHTML; b.textContent = 'Copied'; setTimeout(function () { b.innerHTML = old; }, 1800); };
        if (navigator.clipboard) navigator.clipboard.writeText(text).then(done);
        else { el.select(); document.execCommand('copy'); done(); }
    });

    // ---- Toasts fade out ----
    setTimeout(function () {
        document.querySelectorAll('.toast').forEach(function (t) {
            t.style.transition = 'opacity .4s'; t.style.opacity = 0;
            setTimeout(function () { t.remove(); }, 400);
        });
    }, 5000);
    document.addEventListener('click', function (e) {
        var b = e.target.closest('.toast button');
        if (b) b.parentElement.remove();
    });

    // ---- Chart.js helpers that follow the theme ----
    window.MS = window.MS || {};
    window.MS.css = function (name) { return getComputedStyle(root).getPropertyValue(name).trim(); };
    window.MS.palette = function () {
        return ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--chart-6'].map(window.MS.css);
    };
    window.MS.chart = function (canvasId, buildConfig) {
        var el = document.getElementById(canvasId);
        if (!el || !window.Chart) return;
        var chart;
        function draw() {
            if (chart) chart.destroy();
            Chart.defaults.color = window.MS.css('--text-2');
            Chart.defaults.borderColor = window.MS.css('--border');
            Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
            chart = new Chart(el, buildConfig(window.MS.palette()));
        }
        draw();
        document.addEventListener('themechange', draw);
    };
})();
