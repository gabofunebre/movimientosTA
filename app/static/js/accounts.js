import {
  fetchAccountBalances,
  fetchAccountSummary,
  fetchInkwellBillingData
} from './api.js?v=1';
import { showOverlay, hideOverlay, formatCurrency } from './ui.js?v=1';
import { CURRENCY_SYMBOLS } from './constants.js?v=1';
import { calculateInkwellTotals } from './inkwell_calculator.js?v=1';

const tbody = document.querySelector('#accounts-table tbody');
const refreshBtn = document.getElementById('refresh-accounts');

function renderAccounts(data) {
  tbody.innerHTML = '';
  data.forEach(acc => {
    const tr = document.createElement('tr');
    tr.classList.add('text-center');
    tr.dataset.accountId = acc.account_id;
    const total = formatCurrency(acc.balance);
    const nameTd = document.createElement('td');
    nameTd.textContent = acc.name;
    nameTd.style.color = acc.color;
    const totalTd = document.createElement('td');
    const symbol = CURRENCY_SYMBOLS[acc.currency] || '';
    totalTd.textContent = `${symbol} ${total}`;
    totalTd.classList.add('fw-bold', 'fs-5');
    tr.appendChild(nameTd);
    tr.appendChild(totalTd);
    tr.addEventListener('click', () => toggleDetails(tr, acc));
    tbody.appendChild(tr);
  });
}

async function toggleDetails(row, acc) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains('details')) {
    next.remove();
    return;
  }
  const existing = tbody.querySelector('.details');
  if (existing) existing.remove();
  showOverlay();
  let summary;
  let inkwellTotals = null;
  try {
    summary = await fetchAccountSummary(acc.account_id);
    if (summary.is_billing) {
      try {
        const billingData = await fetchInkwellBillingData();
        inkwellTotals = calculateInkwellTotals(billingData, summary);
      } catch (error) {
        console.error('No se pudo calcular el disponible Inkwell', error);
      }
    }
  } finally {
    hideOverlay();
  }
  const symbol = CURRENCY_SYMBOLS[acc.currency] || '';
  const detailTr = document.createElement('tr');
  detailTr.classList.add('details');
  const detailTd = document.createElement('td');
  detailTd.colSpan = 2;

  const balance =
    Number(summary.opening_balance) +
    Number(summary.income_balance) -
    Number(summary.expense_balance);
  const inkwellIncome = inkwellTotals ? inkwellTotals.income : Number(summary.inkwell_income || 0);
  const inkwellExpense = inkwellTotals ? inkwellTotals.expense : Number(summary.inkwell_expense || 0);
  const inkwellAvailable = inkwellTotals
    ? inkwellTotals.available
    : Number(summary.inkwell_available || 0);
  const total = summary.is_billing
    ? Number(summary.income_balance) - Number(summary.expense_balance) - inkwellAvailable
    : balance;

  let html = '<div class="container text-start">';
  html += '<div class="row g-4 align-items-start">';
  html += '<div class="col-12 col-lg-6">';
  html += `<p><strong>Saldo inicial:</strong> <span class="text-info">${symbol} ${formatCurrency(summary.opening_balance)}</span></p>`;
  html += `<p><strong>Ingresos:</strong> <span class="text-success">${symbol} ${formatCurrency(summary.income_balance)}</span></p>`;
  html += `<p><strong>Egresos:</strong> <span class="text-danger">${symbol} ${formatCurrency(summary.expense_balance)}</span></p>`;
  html += `<p><strong>Balance:</strong> <span class="text-dark fst-italic">${symbol} ${formatCurrency(balance)}</span></p>`;
  html += '</div>';
  if (summary.is_billing) {
    html += '<div class="col-12 col-lg-6">';
    html += '<div class="d-flex justify-content-between align-items-start mb-2">';
    html += '<h5 class="mb-0">Inkwell</h5>';
    html += '<button id="inkwell-details-btn" class="btn btn-outline-primary btn-sm">Detalles Inkwell</button>';
    html += '</div>';
    html += `<p class="mb-1"><strong>Ingresos Inkwell:</strong> <span class="text-success">${symbol} ${formatCurrency(inkwellIncome)}</span></p>`;
    html += `<p class="mb-1"><strong>Egresos Inkwell:</strong> <span class="text-danger">${symbol} ${formatCurrency(inkwellExpense)}</span></p>`;
    html += `<p class="mb-0"><strong>Disponible Inkwell:</strong> <span class="text-dark fw-semibold">${symbol} ${formatCurrency(inkwellAvailable)}</span></p>`;
    html += '</div>';
  }
  html += '</div>';
  html += `<div class="row mt-3"><div class="col text-center"><p class="mb-0"><strong>Total Disponible:</strong> <span class="text-dark fw-bold fs-5">${symbol} ${formatCurrency(total)}</span></p></div></div>`;
  html += '</div>';
  detailTd.innerHTML = html;
  detailTr.appendChild(detailTd);
  row.after(detailTr);
  const detailsBtn = detailTd.querySelector('#inkwell-details-btn');
  if (detailsBtn) {
    detailsBtn.addEventListener('click', event => {
      event.preventDefault();
      window.location.href = '/inkwell.html';
    });
  }
}

async function loadAccounts() {
  showOverlay();
  const data = await fetchAccountBalances();
  renderAccounts(data);
  hideOverlay();
}

refreshBtn.addEventListener('click', loadAccounts);

loadAccounts();
