// api url
const api_url = 
	"https://280a3b62-b510-403b-90ef-3c6a882eaf44.mock.pstmn.io/dexcome/info";

// Function to fetch data from the API endpoint and display it in a table
function fetchData() {
    fetch(api_url)
        .then(response => response.json())
        .then(data => {
            const apiDataTable = document.getElementById('apiDataTable').getElementsByTagName('tbody')[0];
            apiDataTable.innerHTML = ''; // Clear the table body

            for (const key in data) {
                if (data.hasOwnProperty(key)) {
                    const row = apiDataTable.insertRow(apiDataTable.rows.length);
                    const cell1 = row.insertCell(0);
                    const cell2 = row.insertCell(1);
                    cell1.innerHTML = key;
                    cell2.innerHTML = JSON.stringify(data[key]);
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

// Poll for data every 320 seconds (5 minutes and 20 seconds)
function pollData() {
    fetchData(); // Fetch data immediately

    // Set an interval to fetch data periodically
    setInterval(fetchData, 30000); // 320 seconds = 320,000 milliseconds
}

// Call the fetchData function when the page loads
window.onload = pollData;
