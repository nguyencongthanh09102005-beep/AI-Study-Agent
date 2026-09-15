document.addEventListener(
  "DOMContentLoaded",
  function () {

    const canvas =
      document.getElementById(
        "weeklyStudyChart"
      );

    if (
      !canvas ||
      typeof Chart === "undefined"
    ) {
      return;
    }


    const weeklyData =
      Array.isArray(
        window.weeklyStudyData
      )
        ? window.weeklyStudyData
        : [0, 0, 0, 0, 0, 0, 0];


    const context =
      canvas.getContext("2d");


    const gradient =
      context.createLinearGradient(
        0,
        0,
        0,
        280
      );


    gradient.addColorStop(
      0,
      "rgba(100, 88, 255, 0.24)"
    );

    gradient.addColorStop(
      1,
      "rgba(100, 88, 255, 0)"
    );


    const largestValue =
      Math.max(
        ...weeklyData,
        0
      );


    const suggestedMax =
      Math.max(
        2,
        Math.ceil(
          largestValue + 1
        )
      );


    new Chart(
      context,
      {
        type: "line",

        data: {
          labels: [
            "T2",
            "T3",
            "T4",
            "T5",
            "T6",
            "T7",
            "CN"
          ],

          datasets: [
            {
              label: "Giờ học",

              data:
                weeklyData,

              borderColor:
                "#665cff",

              backgroundColor:
                gradient,

              borderWidth:
                3,

              fill:
                true,

              tension:
                0.42,

              pointRadius:
                3,

              pointHoverRadius:
                6,

              pointBackgroundColor:
                "#665cff",

              pointHoverBackgroundColor:
                "#665cff",

              pointHoverBorderColor:
                "#ffffff",

              pointHoverBorderWidth:
                3
            }
          ]
        },


        options: {
          responsive:
            true,

          maintainAspectRatio:
            false,

          interaction: {
            mode:
              "index",

            intersect:
              false
          },

          plugins: {

            legend: {
              display:
                false
            },


            tooltip: {
              backgroundColor:
                "#172033",

              titleColor:
                "#ffffff",

              bodyColor:
                "#ffffff",

              displayColors:
                false,

              padding:
                12,

              callbacks: {

                label(context) {

                  const value =
                    Number(
                      context.parsed.y || 0
                    );


                  return (
                    `${value} giờ học`
                  );
                }
              }
            }
          },


          scales: {

            x: {

              border: {
                display:
                  false
              },

              grid: {
                color:
                  "rgba(133, 143, 166, 0.10)",

                borderDash:
                  [5, 6],

                drawTicks:
                  false
              },

              ticks: {
                color:
                  "#7f889c",

                padding:
                  10,

                font: {
                  size:
                    12,

                  weight:
                    "600"
                }
              }
            },


            y: {

              beginAtZero:
                true,

              suggestedMax:
                suggestedMax,

              border: {
                display:
                  false
              },

              grid: {
                color:
                  "rgba(133, 143, 166, 0.12)",

                borderDash:
                  [5, 6],

                drawTicks:
                  false
              },

              ticks: {
                color:
                  "#7f889c",

                padding:
                  12,

                precision:
                  0
              }
            }
          }
        }
      }
    );

  }
);