(function () {
    function readJson(id, fallback) {
        var el = document.getElementById(id);
        if (!el) return fallback;
        try { return JSON.parse(el.textContent); } catch (e) { return fallback; }
    }

    var scalarsEl = document.getElementById("hub-chart-scalars");
    var s = scalarsEl ? JSON.parse(scalarsEl.textContent) : {};

    var palette = {
        blue: "#2563eb",
        green: "#059669",
        orange: "#ea580c",
        red: "#dc2626",
        purple: "#7c3aed",
        slate: "#94a3b8"
    };
    var gridColor = "rgba(15, 39, 68, 0.06)";

    Chart.defaults.font.family = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif";
    Chart.defaults.color = "#64748b";

    function moneyTick(v) {
        if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
        if (v >= 1e3) return (v / 1e3).toFixed(1) + "k";
        return v;
    }

    function querySuffix() {
        return window.location.search || "";
    }

    function barChart(id, labels, values, label, onClick) {
        var ctx = document.getElementById(id);
        if (!ctx) return;
        new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: label || "USD",
                    data: values,
                    backgroundColor: "rgba(37, 99, 235, 0.8)",
                    borderRadius: 8,
                    borderSkipped: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onHover: onClick ? function (ev, els) { ev.native.target.style.cursor = els.length ? "pointer" : "default"; } : undefined,
                onClick: onClick || undefined,
                plugins: { legend: { display: !!label } },
                scales: {
                    y: { beginAtZero: true, grid: { color: gridColor }, ticks: { callback: moneyTick } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    function doughnut(id, labels, values, colors, onClick) {
        var ctx = document.getElementById(id);
        if (!ctx || !labels.length) return;
        new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: "#fff" }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                onHover: onClick ? function (ev, els) { ev.native.target.style.cursor = els.length ? "pointer" : "default"; } : undefined,
                onClick: onClick || undefined,
                plugins: { legend: { position: "bottom", labels: { boxWidth: 12, padding: 14 } } }
            }
        });
    }

    barChart("chart-revenue-trend", readJson("chart-monthly-labels", []), readJson("chart-monthly-values", []));

    var salesmanReportUrl = s.salesmanReportUrl || ("/reporting/salesman/" + querySuffix());

    doughnut("chart-profit", ["Revenue", "COGS", "OPEX", "Net profit"], [
        Math.max(s.revenue || 0, 0),
        Math.max(s.cogs || 0, 0),
        Math.max(s.opex || 0, 0),
        Math.max(s.netProfit || 0, 0)
    ], [palette.blue, palette.orange, palette.red, palette.green], function (ev, elements) {
        if (!elements.length) return;
        var idx = elements[0].index;
        if (idx === 0) {
            window.location.href = salesmanReportUrl;
        }
    });

    var cashCtx = document.getElementById("chart-cash");
    if (cashCtx) {
        new Chart(cashCtx, {
            type: "bar",
            data: {
                labels: ["In", "Out", "Net"],
                datasets: [{
                    data: [s.cashIn || 0, s.cashOut || 0, (s.cashIn || 0) - (s.cashOut || 0)],
                    backgroundColor: [palette.green, palette.red, palette.blue],
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true, ticks: { callback: moneyTick } } }
            }
        });
    }

    doughnut("chart-ar-ap", ["A/R", "A/P"], [Math.max(s.totalAr || 0, 0), Math.max(s.totalAp || 0, 0)], [palette.blue, palette.orange]);

    doughnut("chart-opex", readJson("chart-opex-labels", []), readJson("chart-opex-values", []), [
        palette.blue, palette.purple, palette.orange, palette.green, palette.red, palette.slate
    ]);

    doughnut("chart-ar-aging", readJson("chart-ar-aging-labels", []), readJson("chart-ar-aging-values", []), [
        palette.green, palette.blue, palette.orange, "#f59e0b", palette.red
    ]);

    var salesmanLabels = readJson("chart-salesman-labels", []);
    var salesmanIds = readJson("chart-salesman-ids", []);
    if (salesmanLabels.length) {
        var salesmanCtx = document.getElementById("chart-salesman");
        if (salesmanCtx) {
            new Chart(salesmanCtx, {
                type: "bar",
                data: {
                    labels: salesmanLabels,
                    datasets: [
                        { label: "Sales", data: readJson("chart-salesman-sales", []), backgroundColor: "rgba(37,99,235,0.75)", borderRadius: 6 },
                        { label: "Profit", data: readJson("chart-salesman-profit", []), backgroundColor: "rgba(5,150,105,0.8)", borderRadius: 6 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    onHover: function (ev, els) { ev.native.target.style.cursor = els.length ? "pointer" : "default"; },
                    onClick: function (ev, elements) {
                        if (!elements.length || !salesmanIds.length) return;
                        var idx = elements[0].index;
                        var empId = salesmanIds[idx];
                        if (empId) {
                            window.location.href = "/reporting/salesman/" + empId + "/brief/" + querySuffix();
                        }
                    },
                    scales: { y: { beginAtZero: true, ticks: { callback: moneyTick } } }
                }
            });
        }
    }

    var destLabels = readJson("chart-destination-labels", []);
    if (destLabels.length) {
        var destCtx = document.getElementById("chart-destinations");
        if (destCtx) {
            new Chart(destCtx, {
                type: "bar",
                data: {
                    labels: destLabels,
                    datasets: [
                        { label: "Sales", data: readJson("chart-destination-sales", []), backgroundColor: "rgba(37,99,235,0.75)", borderRadius: 6 },
                        { label: "Profit", data: readJson("chart-destination-profit", []), backgroundColor: "rgba(5,150,105,0.8)", borderRadius: 6 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true, ticks: { callback: moneyTick } } }
                }
            });
        }
    }

    var supplierLabels = readJson("chart-supplier-labels", []);
    if (supplierLabels.length) {
        var supCtx = document.getElementById("chart-suppliers");
        if (supCtx) {
            new Chart(supCtx, {
                type: "bar",
                data: {
                    labels: supplierLabels,
                    datasets: [{ label: "Owed", data: readJson("chart-supplier-balances", []), backgroundColor: "rgba(234,88,12,0.85)", borderRadius: 6 }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true, ticks: { callback: moneyTick } } }
                }
            });
        }
    }

    var summaryLabels = readJson("chart-summary-labels", []);
    if (summaryLabels.length) {
        barChart("chart-summary", summaryLabels, readJson("chart-summary-values", []), "USD");
    }

    var marginCtx = document.getElementById("chart-margin");
    if (marginCtx) {
        new Chart(marginCtx, {
            type: "doughnut",
            data: {
                labels: ["Net profit est.", "Other costs"],
                datasets: [{
                    data: [
                        Math.max(s.netProfit || 0, 0),
                        Math.max((s.revenue || 0) - (s.netProfit || 0), 0)
                    ],
                    backgroundColor: [palette.green, "#e2e8f0"]
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: { position: "bottom" } } }
        });
    }
})();
