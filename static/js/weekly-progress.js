// Weekly study hours come from completed study_tasks; never substitute sample data.
document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("weeklyStudyChart");
  if (!canvas) return;
  const fallback = document.getElementById("weeklyChartFallback");
  const showFallback = () => {
    canvas.hidden = true;
    if (fallback) fallback.hidden = false;
  };
  if (typeof Chart === "undefined") {
    showFallback();
    return;
  }
  const raw = Array.isArray(window.weeklyStudyData) ? window.weeklyStudyData.slice(0, 7) : [];
  const values = Array.from({ length: 7 }, (_, i) => {
    const n = Number(raw[i]);
    return Number.isFinite(n) ? Math.max(0, n) : 0;
  });
  const ctx = canvas.getContext("2d");
  const fill = ctx.createLinearGradient(0, 0, 0, 260);
  fill.addColorStop(0, "#7664f3");
  fill.addColorStop(1, "#a6b5ff");
  const maxValue = Math.max(...values, 0);
  try {
    new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
      datasets: [{
        label: "Giờ đã học",
        data: values,
        backgroundColor: fill,
        hoverBackgroundColor: "#5f55d8",
        borderRadius: 7,
        borderSkipped: false,
        maxBarThickness: 42
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 350 },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: { label: context =>
            `${Number(context.parsed.y || 0).toLocaleString('vi-VN', {maximumFractionDigits: 2})} giờ` }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: { color: "#687ba0", font: { size: 12, weight: "600" } }
        },
        y: {
          beginAtZero: true,
          suggestedMax: Math.max(2, Math.ceil(maxValue)),
          border: { display: false },
          grid: { color: "rgba(130,148,188,.16)" },
          ticks: { color: "#7c8cac", precision: 0, stepSize: maxValue <= 8 ? 1 : undefined }
        }
      }
    }
    });
  } catch {
    showFallback();
  }
});
