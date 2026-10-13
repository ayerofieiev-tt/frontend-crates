# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from urllib.parse import quote

import pytest

pytest.importorskip("selenium")
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from conformance.utils.tests.test_browser_comparison_layout import click, load, matrix_driver, selection, wait_for_popup
from conformance.utils.src.validate_conformance_status import load_model, validate_unified_only_report

DEFAULTS = ["dynamo_v1@10.0.1", "sglang_python_batch@0.5.14", "vllm_python_batch@0.26.0"]


def test_public_html_and_json_only_contain_unified(rendered_page):
    model = load_model(rendered_page)
    validate_unified_only_report(model)
    assert model["tabs"][0]["label"] == "Unified"
    canonical = Path(__file__).resolve().parents[2] / "CONFORMANCE_v2.json"
    status = json.loads(canonical.read_text())
    assert {row["tab"] for row in status["reports"]} == {"tab-unified"}
    assert status["comparison_defaults"]["tab-unified"] == DEFAULTS
    batch = [capture for capture in status["captures"] if capture["mode"] == "batch"]
    assert len(batch) == 20
    assert all(capture["considered"] == 1868 for capture in batch)
    assert all(capture["attempted"] == capture["captured"] + capture["parser_exception"] for capture in batch)
    assert any(capture["mismatches"] for capture in batch)
    blocked = next(capture for capture in batch if capture["capture"] == "dynamo_v1@9.2.13")
    assert blocked["source_unavailable"] == 1868


@pytest.mark.parametrize("removed", ["tab-toolcalling-batch", "tab-toolcalling-streamv1", "tab-reasoning-batch", "tab-reasoning-stream"])
def test_removed_links_open_unified_with_requested_defaults(matrix_driver, rendered_page, removed):
    d = matrix_driver
    load(d, rendered_page, "?tab=" + removed)
    assert d.execute_script("return [...document.querySelectorAll('.tab-panel')].map(n=>n.id)") == ["tab-unified"]
    assert d.execute_script("return [...document.querySelectorAll('.tab-button')].map(n=>n.textContent.trim())") == ["Unified"]
    assert d.find_element(By.CSS_SELECTOR, ".tab-button").is_displayed()
    assert selection(d)["keys"] == DEFAULTS
    assert len(d.find_elements(By.CSS_SELECTOR, ".engine-card")) == 3


def test_slots_none_duplicates_limits_and_reset(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=" + quote(",".join([DEFAULTS[0], DEFAULTS[0], DEFAULTS[2], DEFAULTS[1]])))
    assert selection(d)["keys"] == [DEFAULTS[0], DEFAULTS[2]]
    assert d.find_element(By.CSS_SELECTOR, ".comparison-notice").is_displayed()
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=,,")
    assert selection(d)["keys"] == []
    assert len(d.find_elements(By.CSS_SELECTOR, ".engine-card")) == 3
    assert d.find_element(By.CSS_SELECTOR, ".comparison-matrix").get_attribute("data-empty") == "true"
    assert not d.find_elements(By.CSS_SELECTOR, ".comparison-matrix .matrix-status")
    d.find_element(By.CSS_SELECTOR, "[data-reset]").click()
    load(d, rendered_page)
    assert selection(d)["keys"] == DEFAULTS
    d.find_element(By.CSS_SELECTOR, ".engine-cards [data-slot-picker='0']").click()
    picker = d.find_element(By.CSS_SELECTOR, "dialog[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("none")
    assert selection(d)["keys"] == DEFAULTS[1:]
    picker.send_keys(Keys.ESCAPE)
    assert d.execute_script("return document.activeElement.dataset.slotPicker") == "0"


def test_same_engine_and_version_implementations_have_distinct_picker_labels(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    d.find_element(By.CSS_SELECTOR, ".engine-cards [data-slot-picker='2']").click()
    options = {option.get_attribute("value"): option.text for option in d.find_elements(By.CSS_SELECTOR, "dialog[open] [data-picker-version] option")}
    python_key = d.execute_script("return window.__CONFORMANCE_PAGE.tabs[0].candidates.find(c=>c.label.startsWith('vLLM Python')&&c.version==='0.26.0'&&c.parse_mode==='unified').key")
    rust_key = d.execute_script("return window.__CONFORMANCE_PAGE.tabs[0].candidates.find(c=>c.label.startsWith('vLLM Rust')&&c.version==='0.26.0').key")
    assert "Python" in options[python_key] and "Rust" in options[rust_key]
    assert "batch" in options[DEFAULTS[2]]
    assert len({options[python_key], options[rust_key], options[DEFAULTS[2]]}) == 3
    d.find_element(By.CSS_SELECTOR, "dialog[open]").send_keys(Keys.ESCAPE)


def test_batch_popup_and_picker_converge_immediately(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    d.find_element(By.CSS_SELECTOR, ".engine-cards [data-slot-picker='0']").click()
    picker = d.find_element(By.CSS_SELECTOR, "dialog[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-version]")).select_by_value("dynamo_v1@9.2.10")
    assert selection(d)["keys"][0] == "dynamo_v1@9.2.10"
    geometry = d.execute_script("const r=document.querySelector('dialog[open]').getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:innerWidth,height:innerHeight}")
    assert geometry["left"] >= 0 and geometry["top"] >= 0
    assert geometry["right"] <= geometry["width"] and geometry["bottom"] <= geometry["height"]
    options = picker.find_elements(By.CSS_SELECTOR, "[data-picker-version] option")
    blocked = next(option for option in options if option.get_attribute("value") == "dynamo_v1@9.2.13")
    assert "source unavailable" in blocked.text
    picker.send_keys(Keys.ESCAPE)
    cell = d.execute_script("const t=window.__CONFORMANCE_PAGE.tabs[0]; const r=t.rows.findIndex(r=>r.family==='gemma4');const c=t.columns.findIndex(c=>c.sub==='tool_only');return document.querySelector('.matrix-cell[data-row=\"'+r+'\"][data-column=\"'+c+'\"]')")
    cell.click()
    popup = wait_for_popup(d)
    text = popup.text
    assert "streaming order/chunk timing unavailable" in text
    assert "reasoning_text=" in text and "normal_text=" in text and "calls=" in text
    assert "Producer:" in text and "source_sha256" in text
    chunk_cells = d.find_elements(By.CSS_SELECTOR, ".comparison-drawer.open tr:not(.ttip-final) td[data-cand='dynamo_v1@9.2.10']")
    assert chunk_cells and all("streaming order/chunk timing unavailable" in cell.text for cell in chunk_cells)
    d.find_element(By.CSS_SELECTOR, ".comparison-drawer.open .drawer-close").click()
    assert not d.find_elements(By.CSS_SELECTOR, ".comparison-drawer.open")
    assert d.execute_script("return document.activeElement.classList.contains('matrix-cell')")


def test_typed_unavailable_reason_and_status_converge_after_picker_change(matrix_driver, rendered_page):
    d = matrix_driver
    key = "vllm_rust@0.26.0"
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=" + quote(key + ",,"))
    position = d.execute_script("""
      const tab=window.__CONFORMANCE_PAGE.tabs[0];
      const row=tab.rows.findIndex(row=>row.family==='gemma4');
      const column=tab.columns.findIndex(column=>column.sub==='guided_json_after_reasoning');
      return {row,column};
    """)
    selector = f".matrix-cell[data-row='{position['row']}'][data-column='{position['column']}']"
    cell = d.find_element(By.CSS_SELECTOR, selector)
    assert cell.find_element(By.CSS_SELECTOR, ".status-request_unsupported")
    click(d, selector, center=True)
    wait_for_popup(d)
    output = d.find_element(By.CSS_SELECTOR, f".comparison-drawer.open .ttip-final td[data-cand='{key}']")
    assert "no GuidedJson/tool-choice request API" in output.text
    assert "[object Object]" not in output.text
    d.find_element(By.CSS_SELECTOR, ".comparison-drawer.open .drawer-close").click()
    d.find_element(By.CSS_SELECTOR, ".engine-cards [data-slot-picker='0']").click()
    picker = d.find_element(By.CSS_SELECTOR, "dialog[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-version]")).select_by_value(DEFAULTS[2])
    assert selection(d)["keys"] == [DEFAULTS[2]]
    assert d.find_element(By.CSS_SELECTOR, selector).find_element(By.CSS_SELECTOR, ".status-request_unsupported")
    picker.send_keys(Keys.ESCAPE)
    click(d, selector, center=True)
    wait_for_popup(d)
    output = d.find_element(By.CSS_SELECTOR, f".comparison-drawer.open .ttip-final td[data-cand='{DEFAULTS[2]}']")
    assert "Legacy batch API cannot apply this authored initialization" in output.text
    assert "[object Object]" not in output.text
    assert all(not node.is_displayed() for node in d.find_elements(
        By.CSS_SELECTOR, f".comparison-drawer.open .ttip-final td[data-cand='{key}']"))
    d.find_element(By.CSS_SELECTOR, ".comparison-drawer.open .drawer-close").click()


def test_detailed_table_uses_the_same_slots_and_golden(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    d.find_element(By.CSS_SELECTOR, ".legacy-report-details > summary").click()

    def assert_detailed_keys(expected):
        state = d.execute_script("""
          const panel=document.querySelector('#tab-unified');
          return {checked:[...panel.querySelectorAll('.cmp-on:checked')].map(e=>e.value),
            references:[...panel.querySelectorAll('.cmp-ref:checked')].map(e=>e.value)};
        """)
        assert sorted(state["checked"]) == sorted(expected)
        assert state["references"] == []
        assert selection(d)["keys"] == expected

    assert_detailed_keys(DEFAULTS)
    assert all(not node.is_displayed() for node in d.find_elements(By.CSS_SELECTOR, ".legacy-report-body .cmprow-ref"))
    d.find_element(By.CSS_SELECTOR, ".engine-cards [data-slot-picker='0']").click()
    picker = d.find_element(By.CSS_SELECTOR, "dialog[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-version]")).select_by_value("dynamo_v1@9.2.10")
    assert_detailed_keys(["dynamo_v1@9.2.10", *DEFAULTS[1:]])
    picker.send_keys(Keys.ESCAPE)
    for slot in range(3):
        d.find_element(By.CSS_SELECTOR, f".engine-cards [data-slot-picker='{slot}']").click()
        picker = d.find_element(By.CSS_SELECTOR, "dialog[open]")
        Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("none")
        picker.send_keys(Keys.ESCAPE)
    assert_detailed_keys([])
    assert not d.find_elements(By.CSS_SELECTOR, ".legacy-report-body td.cell.cmp-eq,.legacy-report-body td.cell.cmp-leak")
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=dynamo_v1%409.2.13,,")
    d.find_element(By.CSS_SELECTOR, ".legacy-report-details > summary").click()
    assert_detailed_keys(["dynamo_v1@9.2.13"])
    assert d.find_elements(By.CSS_SELECTOR, ".comparison-matrix .status-source_unavailable")
    assert d.find_elements(By.CSS_SELECTOR, ".legacy-report-body td.cell.cmp-na")
    assert not d.find_elements(By.CSS_SELECTOR, ".legacy-report-body td.cell.cmp-eq,.legacy-report-body td.cell.cmp-leak")
