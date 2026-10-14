// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
(function () {
  'use strict';

  const page = window.__CONFORMANCE_PAGE;
  const tab = page && page.tabs && page.tabs.find(item => item.id === 'tab-unified');
  const panel = document.getElementById('tab-unified');
  if (!tab || !panel) return;

  const engines = tab.comparison_slot_engines || ['dynamo', 'sglang', 'vllm'];
  const engineNames = { dynamo: 'Dynamo', sglang: 'SGLang', vllm: 'vLLM' };
  const engineLetters = { dynamo: 'D', sglang: 'S', vllm: 'V' };
  const candidates = (tab.candidates || []).filter(item => item && item.key && item.impl !== 'golden');
  const byKey = new Map(candidates.map(item => [item.key, item]));
  const engineName = engine => engine ? engineNames[engine] : 'None';
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
  const preferredByEngine = engines.map(engine => {
    const items = byEngine.get(engine);
    return (items.find(item => item.preferred_default)
      || items.find(item => item.default_bucket === 'A') || items[0] || {}).key || null;
  });
  const preferred = tab.comparison_defaults || preferredByEngine;
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
  const slotEngines = [...engines];
  // Restoration and updates share primary ownership and duplicate prevention.
  function normalizeSlots() {
    if (!slots[0] || !byKey.has(slots[0])) slots[0] = preferred[0];
    const seen = new Set();
    slots.forEach((key, index) => {
      if (!byKey.has(key) || seen.has(key)) slots[index] = null;
      else { seen.add(key); slotEngines[index] = engineOf(byKey.get(key)); }
    });
  }
  initial.slice(0, 3).forEach((key, index) => { slots[index] = key || null; });
  normalizeSlots();

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
  const shortCaptureLabel = (capture, engine) => {
    const label = String(capture && (capture.label || capture.version || capture.key) || 'None');
    const prefix = { dynamo: /^Dynamo\s+/, sglang: /^SGLang(?: Python)?\s+/, vllm: /^vLLM(?: Python)?\s+/ }[engine];
    return label.replace(prefix, '');
  };
  function candidateOptions(engine, slot, selectedKey) {
    const allowNone = slot !== 0;
    const noneOption = allowNone
      ? '<option value=""' + (!selectedKey ? ' selected' : '') + '>None</option>'
      : '';
    if (!engine) return noneOption;
    return noneOption + (byEngine.get(engine) || []).map(item => {
      const duplicate = slots.some((key, index) => index !== slot && key === item.key);
      const missing = !hasCapture(item.key);
      const label = shortCaptureLabel(item, engine);
      return '<option value="' + item.key.replace(/&/g, '&amp;').replace(/"/g, '&quot;') + '"'
        + (selectedKey === item.key ? ' selected' : '') + (duplicate || missing ? ' disabled' : '') + '>'
        + label.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        + (duplicate ? ' — selected in another slot' : missing ? ' — no captured results' : '') + '</option>';
    }).join('');
  }
  controls.innerHTML = slots.map((_key, index) => {
    const engine = slotEngines[index];
    return '<div class="capture-slot" data-engine="' + (engine || 'none') + '">'
      + '<button type="button" class="capture-slot-engine-trigger" data-slot-open="' + index + '"'
      + ' aria-haspopup="dialog" aria-expanded="false" aria-controls="unified-capture-picker"'
      + ' aria-label="Edit comparison slot ' + (index + 1) + ': ' + engineName(engine) + '">'
      + '<span class="capture-slot-badge" data-slot-badge="' + index + '" aria-hidden="true">' + (engineLetters[engine] || '—') + '</span>'
      + '<span class="capture-slot-engine" data-slot-engine="' + index + '">' + engineName(engine) + '</span></button>'
      + '<div class="capture-slot-capture-control" data-slot-capture-control="' + index + '"></div></div>';
  }).join('');
  selector.appendChild(controls);
  panel.insertBefore(selector, panel.querySelector('.cmpctl'));

  const state = { slots, engines: slotEngines };
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
    normalizeSlots();
    selection.keys = state.slots.filter(Boolean);
    window.__applyConformanceSelection(panel, selection.keys, null);
    state.slots.forEach((key, index) => {
      const capture = byKey.get(key);
      const engine = state.engines[index];
      const fullLabel = capture ? capture.label || capture.version || capture.key : 'None';
      const slot = controls.querySelector('.capture-slot:nth-child(' + (index + 1) + ')');
      slot.dataset.engine = engine || 'none';
      slot.querySelector('[data-slot-engine]').textContent = engineName(engine);
      slot.querySelector('[data-slot-badge]').textContent = engineLetters[engine] || '—';
      const captureControl = slot.querySelector('.capture-slot-capture-control');
      if (engine) {
        let captureSelect = captureControl.querySelector('[data-slot-capture]');
        if (!captureSelect) {
          captureSelect = document.createElement('select');
          captureSelect.className = 'capture-slot-select';
          captureSelect.dataset.slotCapture = index;
          captureControl.replaceChildren(captureSelect);
        }
        captureSelect.innerHTML = candidateOptions(engine, index, key);
        captureSelect.value = key || '';
        captureSelect.setAttribute('aria-label', 'Choose capture for comparison slot '
          + (index + 1) + ': ' + engineName(engine) + ', ' + fullLabel);
      } else {
        captureControl.innerHTML = '<span class="capture-slot-none" data-slot-none="' + index + '">None</span>';
      }
      slot.querySelector('[data-slot-open]').setAttribute('aria-label', 'Edit comparison slot ' + (index + 1) + ': ' + engineName(engine));
    });
    persist();
  }
  update();

  const picker = document.createElement('dialog');
  picker.className = 'comparison-picker';
  picker.id = 'unified-capture-picker';
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
  function openPicker(slot, trigger) {
    activeSlot = slot;
    activeTrigger = trigger;
    const engine = state.engines[slot];
    const choices = slot === 0 ? engines : [...engines, 'none'];
    picker.innerHTML = '<h2>Comparison slot ' + (slot + 1) + '</h2>'
      + '<label>Engine <select data-picker-engine>' + choices.map(key => '<option value="' + key + '"'
        + (key === (engine || 'none') ? ' selected' : '') + '>' + engineName(key === 'none' ? null : key) + '</option>').join('')
      + '</select></label>'
      + '<label data-picker-capture-label' + (engine ? '' : ' hidden') + '>Capture <select data-picker-capture>'
      + candidateOptions(engine, slot, state.slots[slot]) + '</select></label>';
    const pickerCapture = picker.querySelector('[data-picker-capture]');
    if (pickerCapture) pickerCapture.value = state.slots[slot] || '';
    trigger.setAttribute('aria-expanded', 'true');
    picker.showModal();
    window.requestAnimationFrame(positionPicker);
  }
  controls.addEventListener('click', event => {
    const trigger = event.target.closest('[data-slot-open]');
    if (trigger) openPicker(Number(trigger.dataset.slotOpen), trigger);
  });
  controls.addEventListener('change', event => {
    if (!event.target.matches('[data-slot-capture]')) return;
    const slot = Number(event.target.dataset.slotCapture);
    const key = event.target.value || null;
    if (key && state.slots.some((value, index) => index !== slot && value === key)) return;
    state.slots[slot] = key;
    update();
  });
  picker.addEventListener('click', event => {
    if (event.target === picker) picker.close();
  });
  picker.addEventListener('close', () => {
    if (activeTrigger && activeTrigger.isConnected) {
      activeTrigger.setAttribute('aria-expanded', 'false');
      activeTrigger.focus({ preventScroll: true });
    }
  });
  picker.addEventListener('change', event => {
    if (event.target.matches('[data-picker-engine]')) {
      const engine = event.target.value === 'none' ? null : event.target.value;
      const captureLabel = picker.querySelector('[data-picker-capture-label]');
      const options = (byEngine.get(engine) || []).filter(item =>
        hasCapture(item.key) && !state.slots.some((key, index) => index !== activeSlot && key === item.key));
      if (activeSlot === 0 && (!engine || !options.length)) {
        event.target.value = state.engines[activeSlot];
        return;
      }
      const current = byKey.get(state.slots[activeSlot]);
      const preferredKey = engine ? preferredByEngine[engines.indexOf(engine)] : null;
      const selected = engine && current && engineOf(current) === engine
        ? current : options.find(item => item.key === preferredKey) || options[0] || null;
      state.engines[activeSlot] = engine;
      state.slots[activeSlot] = selected && selected.key || null;
      captureLabel.hidden = !engine;
      const captureSelect = picker.querySelector('[data-picker-capture]');
      captureSelect.innerHTML = candidateOptions(engine, activeSlot, state.slots[activeSlot]);
      captureSelect.value = state.slots[activeSlot] || '';
      update();
      positionPicker();
    } else if (event.target.matches('[data-picker-capture]')) {
      const key = event.target.value || null;
      if (key && state.slots.some((value, index) => index !== activeSlot && value === key)) return;
      state.slots[activeSlot] = key;
      update();
      positionPicker();
    }
  });
  window.addEventListener('resize', positionPicker);
  window.addEventListener('scroll', positionPicker, true);
})();
