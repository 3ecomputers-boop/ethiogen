/*
 * Collapsible app groups in the admin sidebar.
 *
 * State is per app_label in localStorage, so the sidebar comes back the way it
 * was left rather than resetting every page load.
 *
 * Interaction with Django's own nav_sidebar.js, which also runs here:
 *
 *   - Filtering. That script hides the <tr> of any model whose name does not
 *     match what is typed. If a group is collapsed its rows are display:none
 *     anyway, so a match would be invisible and the box would look broken.
 *     While a filter is active every group is force-expanded, and the saved
 *     state is reapplied once the box is cleared.
 *   - The page you are on is always expanded, otherwise the sidebar would hide
 *     your own location on arrival.
 *
 * Listeners are delegated from document rather than bound per element, so this
 * does not depend on whether it runs before or after nav_sidebar.js (both are
 * loaded with defer).
 */
(function () {
    "use strict";

    var KEY = "ethiogen_admin_nav_collapsed";
    var FILTER_ID = "nav-filter";

    function readCollapsed() {
        try {
            var raw = localStorage.getItem(KEY);
            var parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function writeCollapsed(list) {
        try {
            localStorage.setItem(KEY, JSON.stringify(list));
        } catch (e) {
            /* private mode / quota -- collapsing still works for this page */
        }
    }

    function groups() {
        return Array.prototype.slice.call(
            document.querySelectorAll("#nav-sidebar [data-nav-group]")
        );
    }

    function setGroupState(group, expanded) {
        var body = group.querySelector("[data-nav-body]");
        var button = group.querySelector("[data-nav-toggle]");
        if (body) {
            body.hidden = !expanded;
        }
        if (button) {
            button.setAttribute("aria-expanded", expanded ? "true" : "false");
        }
        group.classList.toggle("eth-nav-group--collapsed", !expanded);
    }

    function isCollapsed(group) {
        return group.classList.contains("eth-nav-group--collapsed");
    }

    function toggleGroup(group) {
        const willExpand = isCollapsed(group);
        setGroupState(group, willExpand);

        var label = group.getAttribute("data-nav-group");
        var list = readCollapsed().filter(function (x) {
            return x !== label;
        });
        if (!willExpand) {
            list.push(label);
        }
        writeCollapsed(list);
    }

    function applyState() {
        var collapsed = readCollapsed();

        groups().forEach(function (group) {
            var label = group.getAttribute("data-nav-group");
            // The app the current page belongs to is deliberately NOT
            // special-cased. It was, and the sidebar lied: clicking the active
            // app collapsed it, then the next page load silently reopened it.
            // The active group is already tinted, so only the user's own saved
            // choice should decide.
            setGroupState(group, collapsed.indexOf(label) === -1);
        });

        updateAllToggle();
    }

    function expandAllForFiltering() {
        groups().forEach(function (group) {
            setGroupState(group, true);
        });
    }

    function updateAllToggle() {
        var toggle = document.getElementById("eth-nav-expand-all");
        if (!toggle) {
            return;
        }
        var anyCollapsed = groups().some(isCollapsed);
        toggle.textContent = anyCollapsed ? "Expand all" : "Collapse all";
        toggle.setAttribute("data-action", anyCollapsed ? "expand" : "collapse");
    }

    function init() {
        if (!document.getElementById("nav-sidebar")) {
            return;
        }

        document.addEventListener("click", function (event) {
            var toggle = event.target.closest("[data-nav-toggle]");
            if (toggle) {
                event.preventDefault();
                toggleGroup(toggle.closest("[data-nav-group]"));
                updateAllToggle();
                return;
            }

            var all = event.target.closest("#eth-nav-expand-all");
            if (all) {
                event.preventDefault();
                var expand = all.getAttribute("data-action") === "expand";
                var collapsed = [];
                groups().forEach(function (group) {
                    setGroupState(group, expand);
                    if (!expand) {
                        collapsed.push(group.getAttribute("data-nav-group"));
                    }
                });
                writeCollapsed(collapsed);
                updateAllToggle();
            }
        });

        // Force everything open while the filter has a value, then restore.
        var filter = document.getElementById(FILTER_ID);
        if (filter) {
            filter.addEventListener("input", function () {
                if (filter.value) {
                    expandAllForFiltering();
                } else {
                    applyState();
                }
            });
            if (filter.value) {
                expandAllForFiltering();
            }
        }

        applyState();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
