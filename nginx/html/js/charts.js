<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

const Charts = {

    instance: null,

    async loadOverview() {

        try {

            const data = await API.statsGet("/overview");

            this.renderOverviewChart(data);

        }
        catch (e) {

            Utils.toast(
                "Error loading metrics",
                "danger"
            );

        }

    },

        renderOverviewChart(data) {

        const ctx =
            document.getElementById("mainChart");

        if (!ctx) return;

        if (this.instance) {

            this.instance.destroy();

        }

        this.instance = new Chart(ctx, {

            type: "bar",

            data: {

                labels: [

                    "Total Requests",

                    "Last 24h",

                    "Active Services",

                    "Active Clients"

                ],

                datasets: [{

                    label: "System Overview",

                    data: [

                        data.total_requests || 0,

                        data.requests_last_24h || 0,

                        data.active_services || 0,

                        data.active_clients || 0

                    ],

                    borderWidth: 1

                }]

            },

            options: {

                responsive: true,

                plugins: {

                    legend: {

                        display: false

                    }

                },

                scales: {

                    y: {

                        beginAtZero: true

                    }

                }

            }

        });

    },

    startAutoRefresh(intervalMs = 10000) {

        this.loadOverview();

        setInterval(() => {

            this.loadOverview();

        }, intervalMs);

    }

};