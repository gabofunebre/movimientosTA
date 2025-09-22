import {
  fetchRetentions,
  createRetention,
  updateRetention,
  deleteRetention,
  fetchWithheldTaxTypes
} from './api.js?v=1';
import {
  renderRetention,
  showOverlay,
  hideOverlay
} from './ui.js?v=1';

const tbody = document.querySelector('#ret-table tbody');
const container = document.getElementById('table-container');
const modalEl = document.getElementById('retModal');
const retModal = new bootstrap.Modal(modalEl);
const form = document.getElementById('ret-form');
const modalTitle = document.getElementById('ret-modal-title');
const alertBox = document.getElementById('ret-alert');
const searchBox = document.getElementById('search-box');
const headers = document.querySelectorAll('#ret-table thead th.sortable');
const addBtn = document.getElementById('add-retention');
const typeSelect = form.tax_type_id;

let retentions = [];
let taxTypes = [];
let taxTypeMap = {};
let sortColumn = 0;
let sortAsc = false;

if (!window.isAdmin && addBtn) {
  addBtn.classList.add('d-none');
}

function populateTaxSelect() {
  typeSelect.innerHTML = '';
  if (!taxTypes.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'Sin impuestos definidos';
    typeSelect.appendChild(opt);
    typeSelect.disabled = true;
    return;
  }
  typeSelect.disabled = false;
  taxTypes.forEach(type => {
    const opt = document.createElement('option');
    opt.value = type.id;
    opt.textContent = type.name;
    typeSelect.appendChild(opt);
  });
}

function updateAddButtonState() {
  if (!addBtn) return;
  if (!window.isAdmin) {
    addBtn.classList.add('d-none');
    return;
  }
  addBtn.disabled = taxTypes.length === 0;
  addBtn.title = taxTypes.length === 0
    ? 'Configure los tipos de impuestos retenidos en la sección de configuración'
    : '';
}

function renderRetentionsTable() {
  const q = searchBox.value.trim().toLowerCase();
  const filtered = retentions.filter(ret => {
    const typeName = (
      taxTypeMap[ret.tax_type_id]?.name || ret.tax_type?.name || ''
    ).toLowerCase();
    const notes = (ret.notes || '').toLowerCase();
    const dateStr = new Date(ret.date)
      .toLocaleDateString('es-ES', {
        day: '2-digit',
        month: 'short',
        year: 'numeric'
      })
      .replace('.', '')
      .toLowerCase();
    return (
      !q ||
      typeName.includes(q) ||
      notes.includes(q) ||
      dateStr.includes(q)
    );
  });

  filtered.sort((a, b) => {
    switch (sortColumn) {
      case 0:
        return sortAsc
          ? new Date(a.date) - new Date(b.date)
          : new Date(b.date) - new Date(a.date);
      case 1: {
        const nameA = taxTypeMap[a.tax_type_id]?.name || a.tax_type?.name || '';
        const nameB = taxTypeMap[b.tax_type_id]?.name || b.tax_type?.name || '';
        return sortAsc ? nameA.localeCompare(nameB) : nameB.localeCompare(nameA);
      }
      case 2:
        return sortAsc
          ? Number(a.amount) - Number(b.amount)
          : Number(b.amount) - Number(a.amount);
      case 3: {
        const notesA = a.notes || '';
        const notesB = b.notes || '';
        return sortAsc ? notesA.localeCompare(notesB) : notesB.localeCompare(notesA);
      }
      default:
        return 0;
    }
  });

  tbody.innerHTML = '';
  filtered.forEach(ret =>
    renderRetention(tbody, ret, taxTypeMap, window.isAdmin ? openEditModal : null, window.isAdmin ? confirmDelete : null)
  );
}

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

async function loadTaxTypes() {
  taxTypes = await fetchWithheldTaxTypes();
  taxTypeMap = Object.fromEntries(taxTypes.map(t => [t.id, t]));
  updateAddButtonState();
}

async function loadRetentions() {
  retentions = await fetchRetentions();
  retentions.forEach(ret => {
    if (ret.tax_type) {
      taxTypeMap[ret.tax_type.id] = ret.tax_type;
    }
  });
  renderRetentionsTable();
}

function openCreateModal() {
  if (!window.isAdmin) return;
  if (!taxTypes.length) {
    alert('Primero configure los tipos de impuestos retenidos en la sección de configuración.');
    return;
  }
  form.reset();
  alertBox.classList.add('d-none');
  form.dataset.mode = 'create';
  delete form.dataset.id;
  modalTitle.textContent = 'Nueva retención';
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  form.date.value = today;
  populateTaxSelect();
  retModal.show();
}

function openEditModal(ret) {
  if (!window.isAdmin) return;
  form.reset();
  alertBox.classList.add('d-none');
  form.dataset.mode = 'edit';
  form.dataset.id = ret.id;
  modalTitle.textContent = 'Editar retención';
  const today = new Date().toISOString().split('T')[0];
  form.date.max = today;
  populateTaxSelect();
  form.date.value = ret.date;
  form.tax_type_id.value = ret.tax_type_id;
  form.amount.value = Number(ret.amount);
  form.notes.value = ret.notes || '';
  retModal.show();
}

async function confirmDelete(ret) {
  if (!window.isAdmin) return;
  const typeName = taxTypeMap[ret.tax_type_id]?.name || ret.tax_type?.name || '';
  const ok = confirm(`¿Eliminar la retención de "${typeName}" del ${ret.date}?`);
  if (!ok) return;
  showOverlay();
  const result = await deleteRetention(ret.id);
  hideOverlay();
  if (result.ok) {
    await loadRetentions();
  } else {
    alert(result.error || 'Error al eliminar');
  }
}

form.addEventListener('submit', async e => {
  e.preventDefault();
  if (!form.reportValidity()) return;
  const data = new FormData(form);
  const payload = {
    date: data.get('date'),
    tax_type_id: parseInt(data.get('tax_type_id'), 10),
    amount: Math.abs(parseFloat(data.get('amount') || '0')),
    notes: (data.get('notes') || '').trim()
  };
  const today = new Date().toISOString().split('T')[0];
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (payload.date > today) {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'La fecha no puede ser futura';
    return;
  }
  if (!payload.tax_type_id) {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'Seleccione un impuesto retenido';
    return;
  }
  if (!payload.amount || payload.amount <= 0) {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = 'El monto debe ser mayor a cero';
    return;
  }
  alertBox.classList.add('d-none');
  showOverlay();
  let result;
  if (form.dataset.mode === 'edit' && form.dataset.id) {
    result = await updateRetention(form.dataset.id, payload);
  } else {
    result = await createRetention(payload);
  }
  hideOverlay();
  alertBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  if (result.ok) {
    alertBox.classList.add('alert-success');
    alertBox.textContent = 'Retención guardada';
    await loadRetentions();
    setTimeout(() => {
      retModal.hide();
      alertBox.classList.add('d-none');
    }, 800);
  } else {
    alertBox.classList.add('alert-danger');
    alertBox.textContent = result.error || 'Error al guardar';
  }
});

if (addBtn) {
  addBtn.addEventListener('click', openCreateModal);
}

searchBox.addEventListener('input', renderRetentionsTable);

headers.forEach((th, index) => {
  th.addEventListener('click', () => {
    if (sortColumn === index) {
      sortAsc = !sortAsc;
    } else {
      sortColumn = index;
      sortAsc = true;
    }
    updateSortIcons();
    renderRetentionsTable();
  });
});

container.addEventListener('scroll', () => {
  if (container.scrollTop + container.clientHeight >= container.scrollHeight - 10) {
    // No hay paginación, pero mantenemos la estructura por consistencia
    renderRetentionsTable();
  }
});

(async function init() {
  showOverlay();
  await loadTaxTypes();
  await loadRetentions();
  populateTaxSelect();
  updateSortIcons();
  hideOverlay();
})();
