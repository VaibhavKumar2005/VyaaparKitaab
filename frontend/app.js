const statusEl = document.getElementById('status');
const btn = document.getElementById('healthBtn');

async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    statusEl.textContent = JSON.stringify(data);
  } catch (err) {
    statusEl.textContent = 'Error: ' + err.message;
  }
}

btn.addEventListener('click', checkHealth);
checkHealth();
