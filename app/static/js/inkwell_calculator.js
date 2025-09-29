function toNumber(value) {
  const num = Number(value ?? 0);
  return Number.isFinite(num) ? num : 0;
}

function classifyRetention(certificate) {
  const name = (certificate?.retained_tax_type?.name || '').toLowerCase();
  if (!name) return 'other';
  if (name.includes('iva')) return 'iva';
  if (name.includes('iibb') || name.includes('ingresos brutos')) return 'iibb';
  return 'other';
}

export function calculateInkwellTotals(billingData, summary) {
  const invoices = Array.isArray(billingData?.invoices) ? billingData.invoices : [];
  const retentions = Array.isArray(billingData?.retention_certificates)
    ? billingData.retention_certificates
    : [];

  const income = toNumber(summary?.inkwell_income);
  const expense = toNumber(summary?.inkwell_expense);

  let purchaseIva = 0;
  let salesIva = 0;
  let sircreb = 0;
  let ivaRetentions = 0;
  let iibbRetentions = 0;
  let perceptions = 0;
  let otherAdditions = 0;

  invoices.forEach(invoice => {
    const ivaAmount = toNumber(invoice?.iva_amount);
    const iibbAmount = toNumber(invoice?.iibb_amount);
    const percepcionesAmount = toNumber(invoice?.percepciones);

    if (invoice?.type === 'purchase') {
      purchaseIva += ivaAmount;
    } else if (invoice?.type === 'sale') {
      salesIva += ivaAmount;
      sircreb += iibbAmount;
    }

    perceptions += percepcionesAmount;
  });

  retentions.forEach(certificate => {
    const amount = toNumber(certificate?.amount);
    const category = classifyRetention(certificate);
    if (category === 'iva') {
      ivaRetentions += amount;
    } else if (category === 'iibb') {
      iibbRetentions += amount;
    } else {
      otherAdditions += amount;
    }
  });

  const additions = purchaseIva + ivaRetentions + iibbRetentions + perceptions + otherAdditions;
  const deductions = salesIva + sircreb;
  const baseAvailable = income - expense;
  const available = baseAvailable + additions - deductions;

  return {
    income,
    expense,
    purchaseIva,
    ivaRetentions,
    iibbRetentions,
    perceptions: perceptions + otherAdditions,
    salesIva,
    sircreb,
    baseAvailable,
    available,
  };
}
