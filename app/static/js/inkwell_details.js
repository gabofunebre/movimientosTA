import { fetchInkwellBillingData } from './api.js?v=1';
import { showOverlay, hideOverlay, formatCurrency } from './ui.js?v=1';

const invoicesTbody = document.querySelector('#inkwell-invoices tbody');
const retentionsTbody = document.querySelector('#inkwell-retentions tbody');
const refreshBtn = document.getElementById('refresh-inkwell');
const alertBox = document.getElementById('inkwell-alert');
const docModalEl = document.getElementById('inkwell-doc-modal');
const docModalTitle = docModalEl?.querySelector('.modal-title') ?? null;
const docModalBody = docModalEl?.querySelector('.modal-body') ?? null;
const hasBootstrap = typeof window !== 'undefined' && window.bootstrap;
const docModal =
  docModalEl && hasBootstrap ? new window.bootstrap.Modal(docModalEl) : null;

function attachRowInteraction(row, onActivate) {
  row.classList.add('cursor-pointer');
  row.setAttribute('role', 'button');
  row.tabIndex = 0;
  row.title = 'Ver detalle';
  row.addEventListener('click', onActivate);
  row.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onActivate();
    }
  });
}


function createDetailList(items, { wrapperClasses = [] } = {}) {
  const wrapper = document.createElement('div');
  wrapper.classList.add('border', 'rounded', 'p-3');
  if (wrapperClasses.length) {
    wrapper.classList.add(...wrapperClasses);
  } else {
    wrapper.classList.add('bg-light');
  }

  const dl = document.createElement('dl');
  dl.classList.add('row', 'mb-0', 'gy-1');

  items.forEach(item => {
    const dt = document.createElement('dt');
    dt.classList.add('col-sm-5', 'col-md-4', 'fw-semibold');
    if (item.emphasis) {
      dt.classList.add('border-top', 'pt-2', 'mt-2');
    }
    dt.textContent = item.label;

    const dd = document.createElement('dd');
    dd.classList.add('col-sm-7', 'col-md-8', 'text-start');
    if (item.align !== 'start') {
      dd.classList.add('text-sm-end');
    }
    if (item.emphasis) {
      dd.classList.add('border-top', 'pt-2', 'mt-2', 'fw-bold', 'fs-5');
    }
    if (item.wrap) {
      dd.classList.add('text-break');
    }
    dd.textContent = item.value;
    dl.append(dt, dd);
  });

  wrapper.appendChild(dl);
  return wrapper;
}


function showDocumentModal(title, items, options) {
  if (!docModal || !docModalTitle || !docModalBody) return;
  docModalTitle.textContent = title;
  docModalBody.innerHTML = '';
  docModalBody.appendChild(createDetailList(items, options));
  docModal.show();
}

function formatDate(value) {
  return new Date(value).toLocaleDateString('es-AR');
}

function getInvoiceTypeText(type) {
  if (type === 'sale') return 'Venta';
  if (type === 'purchase') return 'Compra';
  return type;
}


function showInvoiceDetails(invoice) {
  const baseAmount = Number(invoice.amount ?? 0);
  const ivaAmount = Number(invoice.iva_amount ?? 0);
  const iibbAmount = Number(invoice.iibb_amount ?? 0);
  const percepcionesAmount = Number(invoice.percepciones ?? 0);
  const total = baseAmount + ivaAmount + iibbAmount + percepcionesAmount;
  const numberLabel = invoice.number ? `Factura ${invoice.number}` : `Factura #${invoice.id}`;


  const items = [
    { label: 'Fecha', value: formatDate(invoice.date) },
    { label: 'Tipo', value: getInvoiceTypeText(invoice.type) },

    {
      label: 'Concepto',
      value: invoice.description && invoice.description.trim() ? invoice.description : '—',
      align: 'start',
      wrap: true
    },
    { label: 'Monto sin impuesto', value: `$ ${formatCurrency(baseAmount)}` },

    { label: 'IVA', value: `$ ${formatCurrency(ivaAmount)}` }
  ];

  if (invoice.type === 'sale') {
    items.push({ label: 'Para SIRCREB', value: `$ ${formatCurrency(iibbAmount)}` });
  } else if (invoice.type !== 'purchase') {
    items.push({ label: 'Ingresos Brutos', value: `$ ${formatCurrency(iibbAmount)}` });
  }

  if (invoice.type !== 'sale') {
    items.push({ label: 'Percepciones', value: `$ ${formatCurrency(percepcionesAmount)}` });
  }

  items.push({ label: 'Total', value: `$ ${formatCurrency(total)}`, emphasis: true });

  const wrapperClasses =
    invoice.type === 'purchase'
      ? ['bg-info-subtle']
      : invoice.type === 'sale'
        ? ['bg-success-subtle']
        : [];

  showDocumentModal(numberLabel, items, { wrapperClasses });
}

function showRetentionDetails(certificate) {
  const numberLabel = certificate.number
    ? `Certificado ${certificate.number}`
    : `Certificado #${certificate.id}`;

  showDocumentModal(numberLabel, [
    { label: 'Fecha', value: formatDate(certificate.date) },
    {
      label: 'Tipo de impuesto',
      value: certificate.retained_tax_type?.name || '—',
      wrap: true
    },
    {
      label: 'Factura vinculada',
      value:
        certificate.invoice_reference && certificate.invoice_reference.trim()
          ? certificate.invoice_reference
          : '—',
      wrap: true
    },
    { label: 'Monto retenido', value: `$ ${formatCurrency(Number(certificate.amount ?? 0))}`, emphasis: true }
  ]);
}

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
    const date = formatDate(inv.date);
    const typeText = getInvoiceTypeText(inv.type);
    const amount =
      Number(inv.amount || 0) +
      Number(inv.iva_amount || 0) +
      Number(inv.iibb_amount || 0) +
      Number(inv.percepciones || 0);
    tr.innerHTML =
      `<td class="text-center">${date}</td>` +
      `<td class="text-center">${typeText}</td>` +
      `<td class="text-end">$ ${formatCurrency(amount)}</td>`;
    attachRowInteraction(tr, () => showInvoiceDetails(inv));
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
    const date = formatDate(cert.date);
    const typeName = cert.retained_tax_type?.name || '—';
    tr.innerHTML =
      `<td class="text-center">${date}</td>` +
      `<td class="text-center">${typeName}</td>` +
      `<td class="text-end">$ ${formatCurrency(cert.amount || 0)}</td>`;
    attachRowInteraction(tr, () => showRetentionDetails(cert));
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
