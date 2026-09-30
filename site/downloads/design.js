// ПМ.08: подсказка сопровождает основную форму, сервер проверяет данные.
'use strict';
const designForm = document.querySelector('.stack-form');
if (designForm) {
  const allFields = [...designForm.querySelectorAll('input, select, textarea')];
  const fields = allFields.filter((field, index) => field.type !== 'hidden' && field.required
    && (field.type !== 'radio' || allFields.findIndex(other => other.name === field.name) === index));
  const summary = document.createElement('p');
  summary.className = 'design-summary';
  summary.setAttribute('role', 'status');
  const heading = document.createElement('strong');
  heading.textContent = 'Заполнение формы';
  const counter = document.createElement('span');
  summary.append(heading, counter);
  designForm.prepend(summary);
  function updateSummary() {
    const filled = fields.filter(field => field.type === 'radio'
      ? allFields.some(other => other.name === field.name && other.checked)
      : field.value.trim() !== '').length;
    counter.textContent = `Заполнено ${filled} из ${fields.length} обязательных полей. Проверка выполняется при отправке.`;
  }
  designForm.addEventListener('input', updateSummary);
  designForm.addEventListener('change', updateSummary);
  updateSummary();
}

// Связываем видимые серверные ошибки с соответствующими полями.
const errors = document.querySelectorAll('.field-error');
let firstInvalid = null;
errors.forEach((error, index) => {
  if (!error.id) error.id = `design-error-${index}`;
  const group = error.closest('.field');
  // Поле и его ошибка находятся внутри одной группы .field.
  const input = group ? group.querySelector('input, select, textarea') : null;
  if (!input || !input.matches('input, select, textarea')) return;
  input.setAttribute('aria-invalid', 'true');
  const ids = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
  ids.add(error.id);
  input.setAttribute('aria-describedby', [...ids].join(' '));
  firstInvalid ||= input;
});
if (firstInvalid) firstInvalid.focus();
