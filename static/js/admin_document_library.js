/* Search and filter the Admin shared-document library without altering data.
   The native <details> groups and menus work even when JS is disabled. */
(function () {
  "use strict";

  function init() {
    const root = document.getElementById("adminDocumentLibrary");
    const search = document.getElementById("adminDocSearch");
    const filter = document.getElementById("adminDocFilter");
    const empty = document.getElementById("adminDocEmpty");
    const status = document.getElementById("adminDocStatus");
    if (!root || !search || !filter || !empty || !status) return;

    const groups = Array.from(root.querySelectorAll("[data-admin-document-group]"));
    const menus = Array.from(root.querySelectorAll("[data-admin-doc-menu]"));
    const total = root.querySelectorAll("[data-admin-doc-row]").length;
    const originalDisclosure = new Map();
    let wasFiltering = false;

    function normalize(value) {
      return String(value || "").normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d")
        .toLocaleLowerCase("vi");
    }

    function render() {
      const term = normalize(search.value.trim());
      const kind = filter.value || "all";
      const active = !!term || kind !== "all";
      if (active && !wasFiltering) {
        groups.forEach(group => originalDisclosure.set(group, group.open));
      }

      let shown = 0;
      groups.forEach(group => {
        const rows = Array.from(group.querySelectorAll("[data-admin-doc-row]"));
        let visible = 0;
        rows.forEach(row => {
          const matchesText = !term || normalize(row.dataset.search).includes(term);
          const matchesKind = kind === "all" || row.dataset.kind === kind;
          row.hidden = !matchesText || !matchesKind;
          if (!row.hidden) visible += 1;
        });
        group.hidden = visible === 0;
        const badge = group.querySelector("[data-admin-doc-count]");
        if (badge) badge.textContent = visible + " file";
        if (active && visible) group.open = true;
        shown += visible;
      });

      if (!active && wasFiltering) {
        groups.forEach(group => {
          if (originalDisclosure.has(group)) group.open = originalDisclosure.get(group);
        });
        originalDisclosure.clear();
      }
      wasFiltering = active;
      empty.hidden = shown > 0;
      status.textContent = "Đang hiển thị " + shown + "/" + total + " tài liệu gần đây.";
    }

    function closeMenus(except = null) {
      menus.forEach(menu => { if (menu !== except) menu.open = false; });
    }

    menus.forEach(menu => {
      menu.addEventListener("toggle", () => {
        if (menu.open) closeMenus(menu);
      });
    });

    document.addEventListener("click", event => {
      const target = event.target;
      if (!target || typeof target.closest !== "function" ||
          !target.closest("[data-admin-doc-menu]")) closeMenus();
    });
    document.addEventListener("keydown", event => {
      if (event.key !== "Escape") return;
      const opened = menus.find(menu => menu.open);
      if (opened) {
        closeMenus();
        const trigger = opened.querySelector("summary");
        if (trigger && typeof trigger.focus === "function") trigger.focus();
      }
    });

    search.addEventListener("input", render);
    filter.addEventListener("change", render);
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
