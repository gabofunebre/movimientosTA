import {
  fetchAccounts,
  fetchTransactions,
  createTransaction,
  fetchFrequents,
  fetchExportables,
  updateTransaction,
  deleteTransaction
} from './api.js?v=1';
import {
  renderTransaction,
  populateAccounts,
  showOverlay,
  hideOverlay,
} from './ui.js?v=1';

const tbody = document.querySelector('#tx-table tbody');
const container = document.getElementById('table-container');
const modalEl = document.getElementById('txModal');
const txModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('tx-form');
const alertBox = document.getElementById('tx-alert');
const searchBox = document.getElementById('search-box');
const headers = document.querySelectorAll('#tx-table thead th.sortable');
const freqCheck = document.getElementById('freq-check');
const freqSelect = document.getElementById('freq-select');
const descInput = document.getElementById('desc-input');
const inkwellCheck = document.getElementById('inkwell-check');
const inkwellSelect = document.getElementById('inkwell-select');

let offset = 0;
const limit = 50;
let loading = false;
let accounts = [];
let accountMap = {};
let transactions = [];
let sortColumn = 0;
let sortAsc = false;
let frequents = [];
let frequentMap = {};
let exportables = [];
let exportableMap = {};
let billingAccountId = null;

function renderTransactions() {
  const q = searchBox.value.trim().toLowerCase();
  const filtered = transactions.filter(tx => {
    const accName = accountMap[tx.account_id]?.name.toLowerCase() || '';
    return tx.description.toLowerCase().includes(q) || accName.includes(q);
  });
  filtered.sort((a, b) => {
    switch (sortColumn) {
      case 0:
        return sortAsc
          ? new Date(a.date) - new Date(b.date)
          : new Date(b.date) - new Date(a.date);
      case 1:
        return sortAsc
          ? a.description.localeCompare(b.description)
          : b.description.localeCompare(a.description);
      case 2:
        return sortAsc ? a.amount - b.amount : b.amount - a.amount;
      case 3:
        const accA = accountMap[a.account_id]?.name || '';
        const accB = accountMap[b.account_id]?.name || '';
        return sortAsc ? accA.localeCompare(accB) : accB.localeCompare(accA);
      default:
        return 0;
    }
  });
  tbody.innerHTML = '';
  filtered.forEach(tx => renderTransaction(tbody, tx, accountMap, openEditModal, confirmDelete));
}

async function loadMore() {
  if (loading) return;
  loading = true;
  const data = await fetchTransactions(limit, offset);
  transactions = transactions.concat(data);
  offset += data.length;
  renderTransactions();
  loading = false;
}

function populateAccountSelect(restrictToBilling = false, selectedId = null) {
  let list = accounts.filter(a => a.is_active);
  if (restrictToBilling) {
    list = list.filter(a => a.id === billingAccountId);
  }
  populateAccounts(form.account_id, list);
  if (selectedId !== null && list.some(acc => acc.id === Number(selectedId))) {
    form.account_id.value = String(selectedId);
  } else if (restrictToBilling && billingAccountId && list.length) {
    form.account_id.value = String(billingAccountId);
  }
}

function resetConceptInputs() {
  freqCheck.checked = false;
  freqCheck.disabled = false;
  inkwellCheck.checked = false;
  inkwellCheck.disabled = false;
  descInput.classList.remove('d-none');
  freqSelect.classList.add('d-none');
  inkwellSelect.classList.add('d-none');
  freqSelect.innerHTML = '';
  inkwellSelect.innerHTML = '';
}

function openModal(type) {
  form.reset();
  document.getElementById('form-title').textContent =
    type === 'income' ? 'Nuevo Ingreso' : 'Nuevo Egreso';
  populateAccountSelect(false);
  form.dataset.type = type;
  form.dataset.mode = 'create';
  delete form.dataset.id;
  alertBox.classList.add('d-none');
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = today;
  resetConceptInputs();
  txModal.show();
}

function openEditModal(tx) {
  form.reset();
  const isIncome = tx.amount >= 0;
  document.getElementById('form-title').textContent = isIncome
    ? 'Editar Ingreso'
    : 'Editar Egreso';
  form.dataset.type = isIncome ? 'income' : 'expense';
  form.dataset.mode = 'edit';
  form.dataset.id = tx.id;
  alertBox.classList.add('d-none');
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = tx.date;
  resetConceptInputs();
  descInput.value = tx.description;
  form.amount.value = Math.abs(tx.amount);
  populateAccountSelect(false, tx.account_id);
  form.account_id.value = String(tx.account_id);
  if (tx.exportable_movement_id && exportableMap[tx.exportable_movement_id]) {
    inkwellCheck.checked = true;
    handleInkwellChange();
    if (inkwellCheck.checked) {
      populateInkwellSelect(String(tx.exportable_movement_id));
      inkwellSelect.classList.remove('d-none');
      descInput.classList.add('d-none');
      applyExportable(exportableMap[tx.exportable_movement_id]);
      populateAccountSelect(true, tx.account_id);
    }
  }
  txModal.show();
}

async function confirmDelete(tx) {
  if (!confirm('¿Eliminar movimiento?')) return;
  showOverlay();
  const result = await deleteTransaction(tx.id);
  hideOverlay();
  if (result.ok) {
    transactions = [];
    offset = 0;
    await loadMore();
  } else {
    alert(result.error || 'Error al eliminar');
  }
}

function handleFreqChange() {
  if (freqCheck.checked) {
    inkwellCheck.checked = false;
    inkwellCheck.disabled = true;
    inkwellSelect.classList.add('d-none');
    populateFreqSelect();
    descInput.classList.add('d-none');
    freqSelect.classList.remove('d-none');
    if (freqSelect.value) {
      applyFrequent(frequentMap[freqSelect.value]);
    }
    populateAccountSelect(false, form.account_id.value);
  } else {
    inkwellCheck.disabled = false;
    freqSelect.classList.add('d-none');
    if (!inkwellCheck.checked) {
      descInput.classList.remove('d-none');
    }
  }
}

function handleInkwellChange() {
  const currentAccountId = form.account_id.value ? Number(form.account_id.value) : null;
  if (inkwellCheck.checked) {
    if (!billingAccountId) {
      alert('No hay una cuenta de facturación configurada.');
      inkwellCheck.checked = false;
      return;
    }
    if (!exportables.length) {
      alert('No hay movimientos Inkwell configurados.');
      inkwellCheck.checked = false;
      return;
    }
    freqCheck.checked = false;
    freqCheck.disabled = true;
    freqSelect.classList.add('d-none');
    populateInkwellSelect();
    inkwellSelect.classList.remove('d-none');
    descInput.classList.add('d-none');
    const movement = exportableMap[Number(inkwellSelect.value)];
    applyExportable(movement);
    const targetAccountId = currentAccountId !== null ? currentAccountId : billingAccountId;
    populateAccountSelect(true, targetAccountId);
  } else {
    freqCheck.disabled = false;
    inkwellSelect.classList.add('d-none');
    if (!freqCheck.checked) {
      descInput.classList.remove('d-none');
    }
    populateAccountSelect(false, currentAccountId);
  }
}

document.getElementById('add-income').addEventListener('click', () => openModal('income'));
document.getElementById('add-expense').addEventListener('click', () => openModal('expense'));
searchBox.addEventListener('input', renderTransactions);
freqCheck.addEventListener('change', handleFreqChange);
inkwellCheck.addEventListener('change', handleInkwellChange);

freqSelect.addEventListener('change', () => {
  const f = frequentMap[freqSelect.value];
  if (f) applyFrequent(f);
});

inkwellSelect.addEventListener('change', () => {
  const movement = exportableMap[Number(inkwellSelect.value)];
  if (movement) applyExportable(movement);
});

function populateFreqSelect() {
  freqSelect.innerHTML = '';
  frequents.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.id;
    opt.textContent = f.description;
    freqSelect.appendChild(opt);
  });
  if (freqSelect.options.length > 0) {
    freqSelect.value = freqSelect.options[0].value;
  }
}

function applyFrequent(f) {
  if (!f) return;
  descInput.value = f.description;
}

function populateInkwellSelect(selectedId = null) {
  inkwellSelect.innerHTML = '';
  exportables.forEach(movement => {
    const opt = document.createElement('option');
    opt.value = movement.id;
    opt.textContent = movement.description;
    inkwellSelect.appendChild(opt);
  });
  if (inkwellSelect.options.length > 0) {
    const valueToSelect = selectedId || inkwellSelect.options[0].value;
    inkwellSelect.value = valueToSelect;
  }
}

function applyExportable(movement) {
  if (!movement) return;
  descInput.value = movement.description;
}

headers.forEach((th, index) => {
  th.addEventListener('click', () => {
    if (sortColumn === index) {
      sortAsc = !sortAsc;
    } else {
      sortColumn = index;
      sortAsc = true;
    }
    updateSortIcons();
    renderTransactions();
  });
});

function updateSortIcons() {
  headers.forEach((th, index) => {
    const icon = th.querySelector('.sort-icon');
    if (!icon) return;
    icon.classList.remove('bi-arrow-up', 'bi-arrow-down', 'bi-arrow-down-up');
    if (index === sortColumn) {
      icon.classList.add(sortAsc ? 'bi-arrow-up' : 'bi-arrow-down');
    } else {
      icon.classList.add('bi-arrow-down-up');
    }
  });
}

container.addEventListener('scroll', () => {
  if (container.scrollTop + container.clientHeight >= container.scrollHeight - 10) {
    loadMore();
  }
});

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  let amount = parseFloat(data.get('amount'));
  amount = form.dataset.type === 'expense' ? -Math.abs(amount) : Math.abs(amount);
  const payload = {
    date: data.get('date'),
    description: descInput.value,
    amount,
    notes: '',
    account_id: parseInt(data.get('account_id'), 10),
    exportable_movement_id: null,
  };
  const today = new Date().toISOString().split('T')[0];
  if (payload.date > today) {
    alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'La fecha no puede ser futura';
    return;
  }

  if (inkwellCheck.checked) {
    const selectedId = Number(inkwellSelect.value);
    const movement = exportableMap[selectedId];
    if (!movement) {
      alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
      alertBox.classList.add('alert-danger');
      alertBox.textContent = 'Seleccioná un movimiento Inkwell válido';
      return;
    }
    payload.exportable_movement_id = movement.id;
    payload.description = movement.description;
    payload.account_id = billingAccountId || payload.account_id;
  }

  showOverlay();
  let result;
  if (form.dataset.mode === 'edit' && form.dataset.id) {
    result = await updateTransaction(form.dataset.id, payload);
  } else {
    result = await createTransaction(payload);
  }
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Movimiento guardado';
    transactions = [];
    offset = 0;
    await loadMore();
    setTimeout(() => {
      txModal.hide();
      alertBox.classList.add('d-none');
    }, 1000);
  } else {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = result.error || 'Error al guardar';
  }
});

(async function init() {
  accounts = await fetchAccounts(true);
  accountMap = Object.fromEntries(accounts.map(a => [a.id, a]));
  const billingAccount = accounts.find(a => a.is_billing);
  billingAccountId = billingAccount ? billingAccount.id : null;
  frequents = await fetchFrequents();
  frequentMap = Object.fromEntries(frequents.map(f => [f.id, f]));
  exportables = await fetchExportables();
  exportableMap = Object.fromEntries(exportables.map(m => [m.id, m]));
  await loadMore();
  updateSortIcons();
})();
