async function loadDetections() {

    console.log("FETCHING...");

    let response = await fetch(
        "http://localhost:8000/detections"
    );

    let data = await response.json();

    console.log(data);

    let html = "";

    data.forEach(item => {

        html += `
        <div style="
            background:#ffdddd;
            padding:10px;
            margin:10px;
            border-radius:10px;
        ">
            ${item.label}
        </div>
        `;
    });

    document.getElementById(
        "alerts"
    ).innerHTML = html;
}

loadDetections();

setInterval(loadDetections, 1000);
