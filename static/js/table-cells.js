(function () {
  var DETAIL_HEADERS = /description|details|note|summary|party|client|supplier|name/i;
  var TRUNCATE_LEN = 42;

  function truncateText(text, limit) {
    text = (text || "").trim();
    if (text.length <= limit) return text;
    return text.slice(0, limit - 1).trim() + "…";
  }

  function initTable(root) {
    (root || document).querySelectorAll(".hub-table-wrap table, .app-page__body > table, .panel > table").forEach(function (table) {
      var headers = Array.from(table.querySelectorAll("thead th")).map(function (th) {
        return (th.textContent || "").trim();
      });
      var detailCols = new Set();
      headers.forEach(function (label, index) {
        if (DETAIL_HEADERS.test(label)) detailCols.add(index);
      });

      table.querySelectorAll("tbody tr").forEach(function (row) {
        Array.from(row.children).forEach(function (cell, index) {
          if (cell.classList.contains("num") || cell.querySelector("a, button, input, select, form")) {
            cell.classList.add("cell-nowrap");
            return;
          }
          if (!detailCols.has(index) || cell.classList.contains("cell-detail")) return;
          var full = (cell.textContent || "").trim();
          if (full.length <= TRUNCATE_LEN) return;
          cell.classList.add("cell-detail");
          cell.setAttribute("title", full);
          cell.textContent = truncateText(full, TRUNCATE_LEN);
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTable(document);
  });

  window.initAppTableCells = initTable;
})();
