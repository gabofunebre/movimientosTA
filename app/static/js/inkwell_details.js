import { fetchInkwellBillingData } from './api.js?v=1';
import { showOverlay, hideOverlay, formatCurrency } from './ui.js?v=1';

const invoicesTbody = document.querySelector('#inkwell-invoices tbody');
const retentionsTbody = document.querySelector('#inkwell-retentions tbody');
const refreshBtn = document.getElementById('refresh-inkwell');
const alertBox = document.getElementById('inkwell-alert');

function renderEmptyRow(tbody, message) {
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  td.colSpan = 3;
  td.classList.add('text-center', 'fst-italic');
  td.textContent = message;
  tr.appendChild(td);
  tbody.appendChild(tr);
}

function renderInvoices(invoices) {
  invoicesTbody.innerHTML = '';
  if (!invoices.length) {
    renderEmptyRow(invoicesTbody, 'Sin facturas registradas');
    return;
  }
  invoices.forEach(inv => {
    const tr = document.createElement('tr');
    const date = new Date(inv.date).toLocaleDateString('es-AR');
    const typeText = inv.type === 'sale' ? 'Venta' : inv.type === 'purchase' ? 'Compra' : inv.type;
    const amount =
      Number(inv.amount || 0) +
      Number(inv.iva_amount || 0) +
      Number(inv.iibb_amount || 0) +
      Number(inv.percepciones || 0);
    tr.innerHTML =
      `<td class="text-center">${date}</td>` +
      `<td class="text-center">${typeText}</td>` +
      `<td class="text-end">$ ${formatCurrency(amount)}</td>`;
    invoicesTbody.appendChild(tr);
  });
}

function renderRetentions(retentions) {
  retentionsTbody.innerHTML = '';
  if (!retentions.length) {
    renderEmptyRow(retentionsTbody, 'Sin certificados registrados');
    return;
  }
  retentions.forEach(cert => {
    const tr = document.createElement('tr');
    const date = new Date(cert.date).toLocaleDateString('es-AR');
    const typeName = cert.retained_tax_type?.name || '—';
    tr.innerHTML =
      `<td class="text-center">${date}</td>` +
      `<td class="text-center">${typeName}</td>` +
      `<td class="text-end">$ ${formatCurrency(cert.amount || 0)}</td>`;
    retentionsTbody.appendChild(tr);
  });
}

async function loadData() {
  alertBox.classList.add('d-none');
  alertBox.textContent = '';
  showOverlay();
  try {
    const data = await fetchInkwellBillingData();
    renderInvoices(data.invoices || []);
    renderRetentions(data.retention_certificates || []);
  } catch (error) {
    invoicesTbody.innerHTML = '';
    retentionsTbody.innerHTML = '';
    renderEmptyRow(invoicesTbody, 'Sin datos disponibles');
    renderEmptyRow(retentionsTbody, 'Sin datos disponibles');
    alertBox.textContent = error instanceof Error ? error.message : 'Ocurrió un error inesperado';
    alertBox.classList.remove('d-none');
  } finally {
    hideOverlay();
  }
}

refreshBtn.addEventListener('click', loadData);

loadData();
