document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
    });
  });
  document.querySelectorAll('input[type="month"][data-autosubmit]').forEach(function (m) {
    m.addEventListener("change", function () {
      var form = m.closest("form");
      if (form) form.submit();
    });
  });
  var imp = document.getElementById("import-form");
  if (imp) {
    imp.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = document.getElementById("import-file");
      if (!input.files.length) return;
      var reader = new FileReader();
      reader.onload = function () {
        var meta = document.querySelector('meta[name="csrf"]');
        fetch("/import", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": meta ? meta.getAttribute("content") : ""
          },
          body: reader.result
        })
          .then(function (r) {
            return r.json().then(function (j) {
              window.location = "/export?msg=" + encodeURIComponent(j.message || (j.ok ? "Import réussi" : "Échec")) + "&ok=" + (j.ok ? 1 : 0);
            });
          })
          .catch(function () {
            window.location = "/export?msg=" + encodeURIComponent("Erreur réseau pendant l'import") + "&ok=0";
          });
      };
      reader.readAsText(input.files[0]);
    });
  }
});
