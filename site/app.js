// SPDX-License-Identifier: Apache-2.0
// Small, dependency-free behaviour. Everything degrades gracefully without JS:
// the nav still anchors, the table still filters via /find, nothing is hidden.
(function () {
  "use strict";

  // --- copy-to-clipboard ---------------------------------------------------
  document.querySelectorAll("button.copy").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById(button.dataset.copy);
      if (!target) return;
      var text = target.innerText.replace(/\u00a0/g, " ");
      var done = function () {
        var label = button.textContent;
        button.textContent = "copied";
        setTimeout(function () { button.textContent = label; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var area = document.createElement("textarea");
        area.value = text;
        document.body.appendChild(area);
        area.select();
        try { document.execCommand("copy"); done(); } catch (e) { /* ignore */ }
        document.body.removeChild(area);
      }
    });
  });

  // --- CLI filter ----------------------------------------------------------
  var filter = document.getElementById("cli-filter");
  var table = document.getElementById("cli-table");
  var count = document.getElementById("cli-count");

  if (filter && table && count) {
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
    var total = rows.length;
    var update = function () {
      var query = filter.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (row) {
        var match = query === "" || row.innerText.toLowerCase().indexOf(query) !== -1;
        row.hidden = !match;
        if (match) shown += 1;
      });
      count.textContent = shown === total
        ? total + " commands"
        : shown + " of " + total + " commands";
    };
    filter.addEventListener("input", update);
    filter.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { filter.value = ""; update(); }
    });
    update();
  }

  // --- scrollspy ----------------------------------------------------------
  var links = Array.prototype.slice.call(document.querySelectorAll(".site-nav a"));
  var sections = links
    .map(function (link) {
      var id = link.getAttribute("href").slice(1);
      return { link: link, section: document.getElementById(id) };
    })
    .filter(function (pair) { return Boolean(pair.section); });

  if ("IntersectionObserver" in window && sections.length) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          sections.forEach(function (pair) {
            pair.link.classList.toggle("active", pair.section === entry.target);
          });
        });
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 }
    );
    sections.forEach(function (pair) { observer.observe(pair.section); });
  }
})();
