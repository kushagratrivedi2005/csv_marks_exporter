function CsvGraderXBlock(runtime, element) {
  var parsedRows = [];
  var csvContent = "";
  var $el = $(element);
  function find(sel) { return $el.find(sel); }

  find("#csvgrader-file").on("change", function() {
    if (this.files && this.files[0]) processFile(this.files[0]);
  });

  find("#csvgrader-dropzone").on("dragover", function(e) {
    e.preventDefault(); $(this).addClass("drag-over");
  }).on("dragleave", function() {
    $(this).removeClass("drag-over");
  }).on("drop", function(e) {
    e.preventDefault(); $(this).removeClass("drag-over");
    var f = e.originalEvent.dataTransfer.files[0];
    if (f) processFile(f);
  });

  function processFile(file) {
    var reader = new FileReader();
    reader.onload = function(e) {
      csvContent = e.target.result;
      parsedRows = [];
      csvContent.split("\n").filter(function(l){ return l.trim(); }).forEach(function(line) {
        var parts = line.split(",");
        if (parts.length >= 2)
          parsedRows.push({ username: parts[0].trim(), grade: parseFloat(parts[1].trim()) || 0 });
      });
      showPreview();
      updateBtn();
    };
    reader.readAsText(file);
  }

  function showPreview() {
    var pass = parsedRows.filter(function(r){ return r.grade > 0; }).length;
    find("#csvgrader-stats").html(
      "<div class='csvgrader-stat'><div class='csvgrader-stat-num' style='color:#a080ff'>" + parsedRows.length + "</div><div class='csvgrader-stat-label'>Total</div></div>" +
      "<div class='csvgrader-stat'><div class='csvgrader-stat-num' style='color:#5cfca0'>" + pass + "</div><div class='csvgrader-stat-label'>Pass</div></div>" +
      "<div class='csvgrader-stat'><div class='csvgrader-stat-num' style='color:#fc5c7d'>" + (parsedRows.length - pass) + "</div><div class='csvgrader-stat-label'>Fail</div></div>"
    );
    find("#csvgrader-tbody").html(parsedRows.map(function(r, i) {
      return "<tr><td>" + (i+1) + "</td><td>" + r.username + "</td><td>" + r.grade + "</td></tr>";
    }).join(""));
    find("#csvgrader-preview").show();
  }

  function updateBtn() {
    var hasFile = parsedRows.length > 0;
    var hasTarget = find("#csvgrader-target").val() !== "";
    find("#csvgrader-btn").prop("disabled", !(hasFile && hasTarget));
  }

  find("#csvgrader-target").on("change", updateBtn);

  find("#csvgrader-btn").on("click", function() {
    var target = find("#csvgrader-target").val();
    if (!csvContent || parsedRows.length === 0) { alert("Please select a CSV file first."); return; }
    if (!target) { alert("Please select a target problem block."); return; }

    find("#csvgrader-btn").prop("disabled", true);
    find("#csvgrader-spinner").show();
    find("#csvgrader-result").hide();

    $.ajax({
      type: "POST",
      url: runtime.handlerUrl(element, "import_grades"),
      data: JSON.stringify({
        csv_content: csvContent,
        max_grade: parseFloat(find("#csvgrader-maxgrade").val()) || 1.0,
        target_block: target
      }),
      contentType: "application/json",
      success: function(response) {
        find("#csvgrader-spinner").hide();
        find("#csvgrader-btn").prop("disabled", false);
        if (response.success) {
          var html = "<strong>✓ " + response.summary + "</strong><br><br>";
          response.results.forEach(function(r) {
            html += (r.action === "created" ? "+ " : "↻ ") + r.username + ": " + r.grade + "<br>";
          });
          if (response.errors && response.errors.length) {
            html += "<br><span style='color:#fc5c7d'>Errors:</span><br>";
            response.errors.forEach(function(e) { html += "✗ " + e + "<br>"; });
          }
          find("#csvgrader-result").removeClass("error").addClass("success").html(html).show();
          find("#csvgrader-last").text("Last import: " + response.summary);
        } else {
          find("#csvgrader-result").removeClass("success").addClass("error").html("✗ " + (response.error || "Unknown error")).show();
        }
      },
      error: function(xhr) {
        find("#csvgrader-spinner").hide();
        find("#csvgrader-btn").prop("disabled", false);
        find("#csvgrader-result").removeClass("success").addClass("error").html("✗ Request failed (" + xhr.status + ")").show();
      }
    });
  });
}