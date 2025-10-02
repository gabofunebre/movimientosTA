export async function fetchAccounts(includeInactive = false) {
  const res = await fetch(`/accounts?include_inactive=${includeInactive}`);
  return res.json();
}

export async function fetchTransactions(limit, offset, filters = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  if (filters.account_id) params.append('account_id', filters.account_id);
  if (filters.q) {
    const search = filters.q.trim();
    if (search) params.append('q', search);
  }
  const res = await fetch(`/transactions?${params.toString()}`);
  return res.json();
}

export async function fetchInvoices(limit, offset, filters = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  if (filters.type) params.append('type', filters.type);
  const res = await fetch(`/invoices?${params.toString()}`);
  return res.json();
}

export async function fetchAccountBalances() {
  const res = await fetch('/accounts/balances');
  return res.json();
}

export async function fetchAccountSummary(id) {
  const res = await fetch(`/accounts/${id}/summary`);
  return res.json();
}

export async function createTransaction(payload) {
  const res = await fetch('/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateTransaction(id, payload) {
  const res = await fetch(`/transactions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteTransaction(id) {
  const res = await fetch(`/transactions/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function createInvoice(payload) {
  const res = await fetch('/invoices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) {
      error = data.detail.map(d => d.msg).join(', ');
    } else {
      error = data.detail || error;
    }
  } catch (_) {}
  return { ok: false, error };
}

export async function updateInvoice(id, payload) {
  const res = await fetch(`/invoices/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    if (Array.isArray(data.detail)) {
      error = data.detail.map(d => d.msg).join(', ');
    } else {
      error = data.detail || error;
    }
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteInvoice(id) {
  const res = await fetch(`/invoices/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function createAccount(payload, replaceBilling = false) {
  const res = await fetch(`/accounts?replace_billing=${replaceBilling}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const account = await res.json();
    return { ok: true, account };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateAccount(id, payload, replaceBilling = false) {
  const res = await fetch(`/accounts/${id}?replace_billing=${replaceBilling}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    const account = await res.json();
    return { ok: true, account };
  }
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteAccount(id) {
  const res = await fetch(`/accounts/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function fetchFrequents() {
  const res = await fetch('/frequents');
  return res.json();
}

export async function createFrequent(payload) {
  const res = await fetch('/frequents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateFrequent(id, payload) {
  const res = await fetch(`/frequents/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteFrequent(id) {
  const res = await fetch(`/frequents/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function fetchExportables() {
  const res = await fetch('/movimientos_exportables');
  return res.json();
}

export async function createExportable(payload) {
  const res = await fetch('/movimientos_exportables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function updateExportable(id, payload) {
  const res = await fetch(`/movimientos_exportables/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) return { ok: true };
  let error = 'Error al guardar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function deleteExportable(id) {
  const res = await fetch(`/movimientos_exportables/${id}`, { method: 'DELETE' });
  if (res.ok) return { ok: true };
  let error = 'Error al eliminar';
  try {
    const data = await res.json();
    error = data.detail || error;
  } catch (_) {}
  return { ok: false, error };
}

export async function fetchInkwellBillingData() {
  const res = await fetch('/inkwell/billing-data');
  if (!res.ok) {
    let error = 'No se pudieron obtener los datos de Inkwell';
    try {
      const data = await res.json();
      error = data.detail || error;
    } catch (_) {}
    throw new Error(error);
  }
  return res.json();
}
