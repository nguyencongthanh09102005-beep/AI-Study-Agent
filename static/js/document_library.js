"use strict";

(function () {
  function init() {
    var root = document.getElementById("documentLibrary");
    if (!root) return;
    var tabs = Array.from(root.querySelectorAll("[data-library-tab]"));
    var panels = Array.from(root.querySelectorAll("[data-library-panel]"));
    var search = document.getElementById("documentLibrarySearch");
    var message = document.getElementById("librarySearchStatus");
    var active = "personal";
    var previousOpen = new Map();
    var searching = false;

    function fold(value) {
      var s = String(value || "").toLocaleLowerCase("vi").replace(/đ/g, "d");
      return s.normalize ? s.normalize("NFD").replace(/[\u0300-\u036f]/g, "") : s;
    }

    function updateSearch() {
      var query = fold(search ? search.value.trim() : "");
      var matchedFolders = 0;
      var matchedFiles = 0;
      if (query && !searching) {
        previousOpen = new Map();
        panels.forEach(function (panel) {
          panel.querySelectorAll("[data-library-folder]").forEach(function (folder) {
            previousOpen.set(folder, folder.open);
          });
        });
      }
      if (!query && searching) {
        previousOpen.forEach(function (open, folder) { folder.open = open; });
        previousOpen.clear();
      }
      searching = !!query;

      panels.forEach(function (panel) {
        var isActive = panel.dataset.libraryPanel === active;
        panel.querySelectorAll("[data-library-folder]").forEach(function (folder) {
          var titleMatches = query && fold(folder.dataset.folderName).includes(query);
          var files = Array.from(folder.querySelectorAll("[data-library-file]"));
          var hits = 0;
          files.forEach(function (file) {
            var matches = !query || titleMatches ||
              fold(file.dataset.searchable).includes(query);
            file.hidden = !matches;
            if (matches) hits += 1;
          });
          var show = !query || titleMatches || hits > 0;
          folder.hidden = !show;
          if (query && show) folder.open = true;
          if (isActive && show) {
            matchedFolders++;
            matchedFiles += hits;
          }
        });
      });

      if (message) {
        message.hidden = !query;
        message.textContent = query
          ? (matchedFolders ? "Tìm thấy " + matchedFolders + " môn phù hợp." :
              "Không tìm thấy môn học hoặc tài liệu phù hợp.")
          : "";
      }
    }

    function selectTab(name, focus) {
      if (name !== "personal" && name !== "shared") return;
      active = name;
      tabs.forEach(function (tab) {
        var selected = tab.dataset.libraryTab === name;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
        if (selected && focus) tab.focus();
      });
      panels.forEach(function (panel) {
        panel.hidden = panel.dataset.libraryPanel !== name;
      });
      updateSearch();
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () {
        selectTab(tab.dataset.libraryTab, false);
      });
      tab.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft" &&
            event.key !== "Home" && event.key !== "End") return;
        event.preventDefault();
        var next = index;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = tabs.length - 1;
        selectTab(tabs[next].dataset.libraryTab, true);
      });
    });
    if (search) search.addEventListener("input", updateSearch);
    var fromUrl = new URLSearchParams(window.location.search).get("tab");
    selectTab(fromUrl === "shared" ? "shared" : "personal", false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
