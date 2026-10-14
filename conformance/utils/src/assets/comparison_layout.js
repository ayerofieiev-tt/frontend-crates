// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
(function () {
  'use strict';

  const page = window.__CONFORMANCE_PAGE;
  const tab = page && page.tabs && page.tabs.find(item => item.id === 'tab-unified');
  const panel = document.getElementById('tab-unified');
  if (!tab || !panel) return;

  const engines = ['dynamo', 'sglang', 'vllm'];
  const engineNames = { dynamo: 'Dynamo', sglang: 'SGLang', vllm: 'vLLM' };
  const candidates = (tab.candidates || []).filter(item => item && item.key && item.impl !== 'golden');
  const byKey = new Map(candidates.map(item => [item.key, item]));
  const engineOf = item => {
    const impl = String(item.impl || item.key).toLowerCase();
    return impl.startsWith('dynamo') ? 'dynamo' : impl.startsWith('sglang') ? 'sglang' : 'vllm';
  };
  const hasCapture = key => (tab.rows || []).some(row => Object.values(row.cells || {}).some(cell => {
    const value = cell.cmp && cell.cmp[key];
    return value && value.na !== 1;
  }));
  const available = candidates.filter(item => hasCapture(item.key));
  const byEngine = new Map(engines.map(key => [key, candidates.filter(item => engineOf(item) === key)]));
  const preferred = engines.map(engine => {
    const items = byEngine.get(engine);
    return (items.find(item => item.preferred_default)
      || items.find(item => item.default_bucket === 'A') || items[0] || {}).key || null;
  });
  const params = new URLSearchParams(window.__CONFORMANCE_INITIAL_SEARCH || window.location.search);
  const slotsParam = 'slots_' + tab.id;
  const legacyBaseParam = 'base_' + tab.id;
  const legacyCompareParam = 'cmp_' + tab.id;
  const legacy = params.has(legacyBaseParam) || params.has(legacyCompareParam)
    ? [params.get(legacyBaseParam), ...(params.get(legacyCompareParam) || '').split(',')]
      .filter(key => key && key !== 'golden' && byKey.has(key))
    : null;
  const requested = params.has(slotsParam) ? (params.get(slotsParam) || '').split(',') : legacy;
  const initial = requested === null ? preferred : requested;
  const overflow = initial.filter(Boolean).length > 3;
  const slots = [null, null, null];
  const seen = new Set();
  initial.slice(0, 3).forEach((key, index) => {
    if (key && byKey.has(key) && !seen.has(key)) {
      slots[index] = key;
      seen.add(key);
    }
  });

  const selector = document.createElement('section');
  selector.className = 'capture-slots';
  selector.setAttribute('aria-label', 'Parser captures compared with GOLDEN');
  if (overflow) {
    const notice = document.createElement('p');
    notice.className = 'capture-slots-notice';
    notice.textContent = 'This link selected more than three captures. Showing the first three.';
    selector.appendChild(notice);
  }
  const controls = document.createElement('div');
  controls.className = 'capture-slot-controls';
  const escapeHtml = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  controls.innerHTML = slots.map((key, index) => {
    const capture = byKey.get(key);
    const engine = capture ? engineOf(capture) : engines[index];
    const version = capture ? capture.label || capture.version || capture.key : 'None';
    return '<div class="capture-slot" data-engine="' + engine + '">'
      + '<span class="capture-slot-engine" data-slot-engine="' + index + '">' + engineNames[engine] + '</span>'
      + '<button type="button" class="capture-slot-trigger" data-slot-picker="' + index + '"'
      + ' aria-label="Comparison slot ' + (index + 1) + ': ' + engineNames[engine] + ', ' + escapeHtml(version) + '">'
      + '<span data-slot-label="' + index + '">' + escapeHtml(version) + '</span>'
      + '<span aria-hidden="true">▾</span></button></div>';
  }).join('');
  selector.appendChild(controls);
  panel.insertBefore(selector, panel.querySelector('.cmpctl'));

  const state = { slots };
  const selection = { keys: state.slots.filter(Boolean), reference: null };
  panel._comparisonSelection = selection;
  function persist() {
    const url = new URL(window.location.href);
    const current = state.slots.join(',');
    if (state.slots.every((key, index) => key === preferred[index])) url.searchParams.delete(slotsParam);
    else url.searchParams.set(slotsParam, current);
    url.searchParams.delete(legacyBaseParam);
    url.searchParams.delete(legacyCompareParam);
    window.history.replaceState(null, '', url.toString());
  }
  function update() {
    selection.keys = state.slots.filter(Boolean);
    window.__applyConformanceSelection(panel, selection.keys, null);
    state.slots.forEach((key, index) => {
      const capture = byKey.get(key);
      const label = capture ? capture.label || capture.version || capture.key : 'None';
      const engine = capture ? engineOf(capture) : engines[index];
      const slot = controls.querySelector('.capture-slot:nth-child(' + (index + 1) + ')');
      slot.dataset.engine = engine;
      slot.querySelector('[data-slot-engine]').textContent = capture ? engineNames[engine] : 'Slot ' + (index + 1);
      const button = controls.querySelector('[data-slot-picker="' + index + '"]');
      button.querySelector('[data-slot-label]').textContent = label;
      button.setAttribute('aria-label', 'Comparison slot ' + (index + 1) + ': '
        + (capture ? engineNames[engine] : 'None') + ', ' + label);
    });
    persist();
  }
  update();

  const picker = document.createElement('dialog');
  picker.className = 'capture-picker';
  picker.setAttribute('aria-label', 'Choose engine and capture');
  document.body.appendChild(picker);
  let activeSlot = 0;
  let activeTrigger = null;
  function positionPicker() {
    if (!picker.open || !activeTrigger) return;
    const anchor = activeTrigger.getBoundingClientRect();
    const rect = picker.getBoundingClientRect();
    const margin = 12;
    const gap = 8;
    let left = anchor.right + gap;
    if (left + rect.width > window.innerWidth - margin) left = anchor.left - rect.width - gap;
    picker.style.left = Math.max(margin, Math.min(left, window.innerWidth - rect.width - margin)) + 'px';
    picker.style.top = Math.max(margin, Math.min(anchor.top, window.innerHeight - rect.height - margin)) + 'px';
  }
  function candidateOptions(engine) {
    return (byEngine.get(engine) || []).map(item => {
      const duplicate = state.slots.some((key, index) => index !== activeSlot && key === item.key);
      const missing = !hasCapture(item.key);
      const label = item.label || item.version || item.key;
      return '<option value="' + item.key.replace(/&/g, '&amp;').replace(/"/g, '&quot;') + '"'
        + (state.slots[activeSlot] === item.key ? ' selected' : '') + (duplicate || missing ? ' disabled' : '') + '>'
        + label.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        + (duplicate ? ' — selected in another slot' : missing ? ' — no captured results' : '') + '</option>';
    }).join('');
  }
  function openPicker(slot, trigger) {
    activeSlot = slot;
    activeTrigger = trigger;
    const selected = byKey.get(state.slots[slot]);
    const engine = selected ? engineOf(selected) : engines[slot];
    picker.innerHTML = '<form method="dialog"><h2>Comparison slot ' + (slot + 1) + '</h2>'
      + '<label>Engine <select data-picker-engine>' + engines.map(key => '<option value="' + key + '"'
        + (key === engine ? ' selected' : '') + '>' + engineNames[key] + '</option>').join('')
      + '<option value="none">None</option></select></label>'
      + '<label>Capture <select data-picker-capture>' + candidateOptions(engine) + '</select></label>'
      + '<button type="button" data-picker-close>Done</button></form>';
    picker.showModal();
    window.requestAnimationFrame(positionPicker);
  }
  controls.addEventListener('click', event => {
    const trigger = event.target.closest('[data-slot-picker]');
    if (trigger) openPicker(Number(trigger.dataset.slotPicker), trigger);
  });
  picker.addEventListener('click', event => {
    if (event.target === picker || event.target.closest('[data-picker-close]')) picker.close();
  });
  picker.addEventListener('close', () => {
    if (activeTrigger && activeTrigger.isConnected) activeTrigger.focus({ preventScroll: true });
  });
  picker.addEventListener('change', event => {
    if (event.target.matches('[data-picker-engine]')) {
      const engine = event.target.value;
      if (engine === 'none') {
        state.slots[activeSlot] = null;
        update();
        event.target.value = 'none';
        picker.querySelector('[data-picker-capture]').disabled = true;
        return;
      }
      const options = (byEngine.get(engine) || []).filter(item =>
        hasCapture(item.key) && !state.slots.some((key, index) => index !== activeSlot && key === item.key));
      if (!options.length) return;
      const current = byKey.get(state.slots[activeSlot]);
      const selected = options.find(item => current && item.key === current.key) || options[0];
      picker.querySelector('[data-picker-capture]').innerHTML = candidateOptions(engine);
      picker.querySelector('[data-picker-capture]').value = selected.key;
      picker.querySelector('[data-picker-capture]').disabled = false;
      state.slots[activeSlot] = selected.key;
      update();
    } else if (event.target.matches('[data-picker-capture]')) {
      const key = event.target.value;
      if (state.slots.some((value, index) => index !== activeSlot && value === key)) return;
      state.slots[activeSlot] = key;
      update();
    }
  });
  window.addEventListener('resize', positionPicker);
  window.addEventListener('scroll', positionPicker, true);
})();
