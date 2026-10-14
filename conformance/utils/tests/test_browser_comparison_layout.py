# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

import pytest

pytest.importorskip("selenium")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

pytestmark = pytest.mark.skipif(
    not any(shutil.which(binary) for binary in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")),
    reason="no headless Chrome available",
)

DEFAULTS = ["dynamo_v1@10.0.1"]
DEFAULT_SLOTS = ["dynamo_v1@10.0.1", None, None]


@pytest.fixture(scope="module")
def matrix_driver():
    options = Options()
    for argument in ("--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--window-size=2400,1200"):
        options.add_argument(argument)
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()


def load(driver, rendered_page: Path, query=""):
    driver.get(rendered_page.resolve().as_uri() + query)
    WebDriverWait(driver, 20).until(lambda browser: browser.find_elements(By.CSS_SELECTOR, ".tab-panel.active .capture-slots"))
    WebDriverWait(driver, 20).until(lambda browser: browser.find_elements(By.CSS_SELECTOR, ".tab-panel.active table[data-parity-table]"))


def selection(driver):
    return driver.execute_script("const s=document.querySelector('.tab-panel.active')._comparisonSelection;return {keys:s.keys,reference:s.reference}")


def wait_for_popup(driver):
    return WebDriverWait(driver, 10).until(lambda browser: browser.find_element(By.CSS_SELECTOR, ".tab-panel.active .ttip-visible"))


def choose_slot(driver, slot, engine, capture=None, *, close=True):
    driver.find_element(By.CSS_SELECTOR, f".capture-slot [data-slot-open='{slot}']").click()
    picker = driver.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value(engine)
    if capture is not None:
        Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value(capture)
    if close and picker.is_displayed():
        picker.send_keys(Keys.ESCAPE)
    return picker


def picker_capture_keys(driver, picker):
    return driver.execute_script("""
      const picker = arguments[0];
      const engine = picker.querySelector('[data-picker-engine]').value;
      const tab = window.__CONFORMANCE_PAGE.tabs.find(item => item.id === 'tab-unified');
      const expected = (tab.candidates || [])
        .filter(item => String(item.impl || item.key).toLowerCase().startsWith(engine))
        .map(item => item.key).sort();
      const actual = [...picker.querySelectorAll('[data-picker-capture] option')]
        .map(option => option.value).filter(Boolean).sort();
      return {engine, expected, actual};
    """, picker)


def test_unified_report_keeps_the_original_table_and_hides_its_single_tab(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?tab=tab-toolcalling-batch")
    assert d.execute_script("return [...document.querySelectorAll('.tab-panel')].map(node=>node.id)") == ["tab-unified"]
    assert not d.find_elements(By.CSS_SELECTOR, ".tab-button")
    assert d.find_element(By.CSS_SELECTOR, ".tab-panel.active table[data-parity-table]").is_displayed()
    assert not d.find_elements(By.CSS_SELECTOR, ".comparison-matrix,.engine-score,.category-chips,.comparison-legend")
    assert d.find_element(By.CSS_SELECTOR, "[data-view-detailed]").is_displayed()
    assert d.find_element(By.CSS_SELECTOR, "[data-transpose-toggle]").is_displayed()


def test_three_capture_slots_drive_the_original_report(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    assert selection(d) == {"keys": DEFAULTS, "reference": None}
    assert len(d.find_elements(By.CSS_SELECTOR, ".capture-slot [data-slot-capture]")) == 3
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-capture='0']").get_attribute("value") == DEFAULTS[0]
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-capture='0']").get_attribute("aria-label") == "Choose capture for comparison slot 1: Dynamo, 10.0.1 · v2 batch"
    assert not d.find_elements(By.CSS_SELECTOR, ".capture-slot [data-slot-capture='0'] option[value='']")
    assert [element.text for element in d.find_elements(By.CSS_SELECTOR, ".capture-slot [data-slot-engine]")] == ["Dynamo", "SGLang", "vLLM"]
    assert [d.find_element(By.CSS_SELECTOR, f"[data-slot-capture='{slot}']").get_attribute("value") for slot in (1, 2)] == ["", ""]
    assert len(d.find_elements(By.CSS_SELECTOR, "[data-slot-capture='1'] option[value=''],[data-slot-capture='2'] option[value='']")) == 2
    Select(d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']")).select_by_value("dynamo_v1@9.2.10")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    assert not d.find_elements(By.CSS_SELECTOR, ".comparison-picker[open]")
    Select(d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']")).select_by_value(DEFAULTS[0])
    assert selection(d)["keys"] == DEFAULTS

    choose_slot(d, 0, "dynamo", "dynamo_v1@9.2.10")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-engine='0']").text.upper() == "DYNAMO"
    assert d.find_element(By.CSS_SELECTOR, ".tab-panel.active table[data-parity-table]").is_displayed()
    checked = d.execute_script("return [...document.querySelectorAll('#tab-unified .cmp-on:checked')].map(input=>input.value)")
    assert sorted(checked) == sorted(selection(d)["keys"])
    detailed = d.find_element(By.CSS_SELECTOR, "[data-view-detailed]")
    detailed.click()
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    checked = d.execute_script("return [...document.querySelectorAll('#tab-unified .cmp-on:checked')].map(input=>input.value)")
    assert sorted(checked) == sorted(selection(d)["keys"])
    detailed.click()
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]


def test_same_engine_versions_none_and_duplicate_prevention(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    choose_slot(d, 0, "dynamo", "dynamo_v1@9.2.10")
    picker = choose_slot(d, 1, "dynamo", "dynamo_v1@9.2.7", close=False)
    assert selection(d)["keys"][:2] == ["dynamo_v1@9.2.10", "dynamo_v1@9.2.7"]
    duplicate = picker.find_element(By.CSS_SELECTOR, "option[value='dynamo_v1@9.2.10']")
    assert duplicate.get_attribute("disabled")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("none")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-engine='1']").text == "None"


def test_primary_slot_cannot_be_empty_and_engine_change_selects_a_version(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=%2C%2C")
    assert selection(d)["keys"] == DEFAULTS
    d.find_element(By.CSS_SELECTOR, "[data-slot-open='0']").click()
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    assert not picker.find_elements(By.CSS_SELECTOR, "[data-picker-capture] option[value='']")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("sglang")
    selected = selection(d)["keys"]
    assert len(selected) == 1 and selected[0].startswith("sglang_python")
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']").get_attribute("value") == selected[0]


def test_none_slot_card_and_picker_keep_the_capture_control(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    assert not d.execute_script("return new URL(location.href).searchParams.has('slots_tab-unified')")
    choose_slot(d, 2, "none")

    card = d.find_element(By.CSS_SELECTOR, ".capture-slot[data-engine='none']")
    trigger = card.find_element(By.CSS_SELECTOR, "[data-slot-open='2']")
    assert trigger.text == "None"
    assert card.find_element(By.CSS_SELECTOR, "[data-slot-none='2']").text == "No comparison selected"
    geometry = d.execute_script("const r=arguments[0].getBoundingClientRect();return [r.width,r.height,innerWidth]", card)
    assert geometry[0] > 1000 and geometry[1] >= 318
    theme_colors = d.execute_script("""
      const root = document.documentElement;
      const original = root.getAttribute('data-theme');
      const slot = arguments[0];
      const trigger = slot.querySelector('.capture-slot-engine-trigger');
      const note = slot.querySelector('.capture-slot-none');
      const styles = {};
      for (const theme of ['light', 'dark']) {
        root.setAttribute('data-theme', theme);
        styles[theme] = {
          card: getComputedStyle(slot).backgroundColor,
          button: getComputedStyle(trigger).backgroundColor,
          buttonText: getComputedStyle(trigger).color,
          noteText: getComputedStyle(note).color
        };
      }
      if (original === null) root.removeAttribute('data-theme');
      else root.setAttribute('data-theme', original);
      return styles;
    """, card)
    assert theme_colors == {
        "light": {"card": "rgb(255, 255, 255)", "button": "rgb(255, 255, 255)", "buttonText": "rgb(17, 24, 39)", "noteText": "rgb(17, 24, 39)"},
        "dark": {"card": "rgb(23, 27, 33)", "button": "rgb(23, 27, 33)", "buttonText": "rgb(232, 237, 243)", "noteText": "rgb(232, 237, 243)"},
    }

    trigger.click()
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    capture_label = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture-label]")
    capture_select = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")
    assert capture_label.is_displayed()
    assert capture_label.text.startswith("Capture")
    assert capture_select.get_attribute("disabled") is not None
    assert not Select(capture_select).options
    popup_geometry = d.execute_script("""
      const popup = arguments[0];
      const bounds = popup.getBoundingClientRect();
      const engineLabel = popup.querySelector('[data-picker-engine]').closest('label');
      const captureLabel = popup.querySelector('[data-picker-capture-label]');
      const engine = popup.querySelector('[data-picker-engine]');
      const capture = popup.querySelector('[data-picker-capture]');
      const engineBounds = engine.getBoundingClientRect();
      const captureBounds = capture.getBoundingClientRect();
      const engineLabelBounds = engineLabel.getBoundingClientRect();
      const captureLabelBounds = captureLabel.getBoundingClientRect();
      return {
        bounds: [bounds.left, bounds.top, bounds.right, bounds.bottom, innerWidth, innerHeight],
        ratio: bounds.width / bounds.height,
        engineSize: [engineBounds.width, engineBounds.height],
        captureSize: [captureBounds.width, captureBounds.height],
        rowX: [engineBounds.left, captureBounds.left],
        rowY: [engineLabelBounds.top, captureLabelBounds.top],
        rowCenters: [engineBounds.top + engineBounds.height / 2, captureBounds.top + captureBounds.height / 2,
          engineLabelBounds.top + engineLabelBounds.height / 2, captureLabelBounds.top + captureLabelBounds.height / 2]
      };
    """, picker)
    assert popup_geometry["bounds"][0] >= 0 and popup_geometry["bounds"][2] <= popup_geometry["bounds"][4]
    assert popup_geometry["bounds"][1] >= 0 and popup_geometry["bounds"][3] <= popup_geometry["bounds"][5]
    assert popup_geometry["ratio"] > 2
    assert popup_geometry["engineSize"][1] == popup_geometry["captureSize"][1] == 58
    assert abs(popup_geometry["rowX"][0] - popup_geometry["rowX"][1]) <= 1
    assert popup_geometry["rowY"][0] < popup_geometry["rowY"][1]
    assert all(abs(popup_geometry["rowCenters"][index] - popup_geometry["rowCenters"][index + 2]) <= 1 for index in (0, 1))
    picker.send_keys(Keys.ESCAPE)
    assert d.execute_script("return new URL(location.href).searchParams.get('slots_tab-unified')") == "dynamo_v1@10.0.1,,none"
    d.refresh()
    WebDriverWait(d, 10).until(lambda browser: browser.find_element(By.CSS_SELECTOR, ".capture-slot[data-engine='none'] [data-slot-open='2']"))
    assert selection(d) == {"keys": DEFAULTS, "reference": None}
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot[data-engine='none'] [data-slot-open='2']").text == "None"

    choose_slot(d, 1, "dynamo")
    Select(d.find_element(By.CSS_SELECTOR, "[data-slot-capture='1']")).select_by_value("")
    assert d.execute_script("return new URL(location.href).searchParams.get('slots_tab-unified')") == "dynamo_v1@10.0.1,@dynamo,none"
    d.refresh()
    WebDriverWait(d, 20).until(lambda browser: browser.find_element(By.CSS_SELECTOR, ".capture-slot[data-engine='dynamo'] [data-slot-capture='1']"))
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-capture='1']").get_attribute("value") == ""
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot[data-engine='none'] [data-slot-open='2']").text == "None"


def test_dynamo_capture_labels_name_the_unified_batch_corpus(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    option = d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0'] option[value='dynamo_v1@10.0.1']")
    assert option.text == "10.0.1 · v2 batch"
    assert "Dynamo v1 parser" in option.get_attribute("title")
    assert "without a jail buffer" in option.get_attribute("title")


def test_engine_badges_open_live_picker_without_a_done_button(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    for slot, engine in enumerate(("dynamo", "sglang", "vllm")):
        d.find_element(By.CSS_SELECTOR, f"[data-slot-open='{slot}']").click()
        picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
        assert picker.find_element(By.TAG_NAME, "h2").text == f"Comparison slot {slot + 1}"
        assert not picker.find_elements(By.CSS_SELECTOR, "button")
        assert Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).first_selected_option.get_attribute("value") == engine
        assert [option.get_attribute("value") for option in Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).options] == ["dynamo", "sglang", "vllm"] + (["none"] if slot > 0 else [])
        capture_label = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture-label]")
        assert capture_label.is_displayed()
        assert Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).first_selected_option.get_attribute("value") == (DEFAULT_SLOTS[slot] or "")
        scoped_options = picker_capture_keys(d, picker)
        assert scoped_options["engine"] == engine
        assert scoped_options["actual"] == scoped_options["expected"]
        if slot == 0:
            style = d.execute_script("const p=getComputedStyle(arguments[0]),s=getComputedStyle(arguments[0].querySelector('select'));return {background:p.backgroundColor,border:p.borderTopColor,select:s.backgroundColor,color:p.color}", picker)
            assert style == {
                "background": "rgb(255, 255, 255)",
                "border": "rgb(207, 213, 220)",
                "select": "rgb(241, 243, 246)",
                "color": "rgb(17, 24, 39)",
            }
        picker.send_keys(Keys.ESCAPE)
    assert selection(d)["keys"] == DEFAULTS

    d.find_element(By.CSS_SELECTOR, "[data-slot-open='1']").click()
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("sglang")
    scoped_options = picker_capture_keys(d, picker)
    assert scoped_options["actual"] == scoped_options["expected"]
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("vllm")
    scoped_options = picker_capture_keys(d, picker)
    assert scoped_options["actual"] == scoped_options["expected"]
    assert selection(d)["keys"] == [*DEFAULTS, "vllm_python_batch@0.26.0"]
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-capture='1']").get_attribute("value") == "vllm_python_batch@0.26.0"
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value("vllm_python_batch@0.26.0")
    assert selection(d)["keys"] == [*DEFAULTS, "vllm_python_batch@0.26.0"]
    assert picker.is_displayed()
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value("")
    assert selection(d)["keys"] == DEFAULTS
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-engine='1']").text == "vLLM"
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("none")
    assert selection(d)["keys"] == DEFAULTS
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-engine='1']").text == "None"
    capture_label = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture-label]")
    capture_select = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")
    assert capture_label.is_displayed() and capture_select.get_attribute("disabled") is not None
    assert not Select(capture_select).options
    picker.send_keys(Keys.ESCAPE)
    d.find_element(By.CSS_SELECTOR, "[data-slot-open='1']").click()
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    assert Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).first_selected_option.get_attribute("value") == "none"
    capture_label = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture-label]")
    capture_select = picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")
    assert capture_label.is_displayed() and capture_select.get_attribute("disabled") is not None
    assert not Select(capture_select).options
    picker.send_keys(Keys.ESCAPE)


def test_legacy_links_are_capped_and_picker_stays_anchored(matrix_driver, rendered_page):
    d = matrix_driver
    keys = ["dynamo_v1@9.2.10", "dynamo_v1@9.2.7", "sglang_python_batch@0.5.14", "vllm_python_batch@0.26.0"]
    query = "?tab=tab-unified&base_tab-unified=" + quote(keys[0]) + "&cmp_tab-unified=" + quote(",".join(keys[1:]))
    load(d, rendered_page, query)
    assert selection(d)["keys"] == keys[:3]
    assert "more than three captures" in d.find_element(By.CSS_SELECTOR, ".capture-slots-notice").text

    trigger = d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-open='2']")
    trigger.click()
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    geometry = d.execute_script("const a=arguments[0].getBoundingClientRect(),p=arguments[1].getBoundingClientRect();return {left:p.left,right:p.right,top:p.top,bottom:p.bottom,w:innerWidth,h:innerHeight,gap:Math.min(Math.abs(a.right-p.left),Math.abs(p.right-a.left))}", trigger, picker)
    assert geometry["left"] >= 0 and geometry["top"] >= 0
    assert geometry["right"] <= geometry["w"] and geometry["bottom"] <= geometry["h"]
    assert geometry["gap"] <= 9
    picker.send_keys(Keys.ESCAPE)
    assert d.execute_script("return document.activeElement.dataset.slotOpen") == "2"

    trigger.click()
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    d.execute_script("arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true}))", picker)
    assert not d.find_elements(By.CSS_SELECTOR, ".comparison-picker[open]")
    assert d.execute_script("return document.activeElement.dataset.slotOpen") == "2"


@pytest.mark.parametrize("legacy_query", [
    "cmp_tab-unified=vllm_rust",
    "base_tab-unified=removed-parser&cmp_tab-unified=vllm_rust",
    "base_tab-unified=&cmp_tab-unified=vllm_rust",
])
def test_legacy_compare_keeps_default_primary_when_base_is_missing_or_invalid(matrix_driver, rendered_page, legacy_query):
    d = matrix_driver
    load(d, rendered_page, "?tab=tab-unified&" + legacy_query)
    assert selection(d)["keys"] == [DEFAULTS[0], "vllm_rust"]
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']").get_attribute("value") == DEFAULTS[0]
    assert d.execute_script("return new URL(location.href).searchParams.get('slots_tab-unified')") == "dynamo_v1@10.0.1,vllm_rust,"
    d.refresh()
    WebDriverWait(d, 20).until(lambda browser: browser.find_elements(By.CSS_SELECTOR, ".tab-panel.active .capture-slots"))
    assert selection(d)["keys"] == [DEFAULTS[0], "vllm_rust"]


def test_restored_empty_primary_owns_default_without_duplicate(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?slots_tab-unified=%2Cdynamo_v1%4010.0.1%2C")
    assert selection(d)["keys"] == DEFAULTS
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-capture='1']").get_attribute("value") == ""


def test_narrow_picker_repositions_when_none_expands(matrix_driver, rendered_page):
    d = matrix_driver
    d.set_window_size(430, 700)
    try:
        load(d, rendered_page)
        choose_slot(d, 2, "none")
        picker = choose_slot(d, 2, "dynamo", close=False)
        geometry = d.execute_script("const r=arguments[0].getBoundingClientRect();return [r.left,r.right,r.top,r.bottom,innerWidth,innerHeight]", picker)
        assert 0 <= geometry[0] < geometry[1] <= geometry[4]
        assert 0 <= geometry[2] < geometry[3] <= geometry[5]
        assert [option.get_attribute("value") for option in Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).options] == ["dynamo", "sglang", "vllm", "none"]
    finally:
        d.set_window_size(2400, 1200)


def test_segments_click_only_popup_keyboard_and_immediate_selection(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    cell = d.find_element(By.CSS_SELECTOR, "#tab-unified td.cell[data-cmp][data-ttip-id]")
    assert len(cell.find_elements(By.CSS_SELECTOR, ".matrix-status")) == 1
    d.execute_script("arguments[0].dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));arguments[0].focus()", cell)
    assert not cell.find_elements(By.CSS_SELECTOR, ".ttip-built")
    assert not d.find_elements(By.CSS_SELECTOR, ".ttip-visible")
    cell.send_keys(Keys.ENTER)
    popup = WebDriverWait(d, 10).until(lambda b: b.find_element(By.CSS_SELECTOR, "body > .ttip-visible"))
    bounds = d.execute_script("const r=arguments[0].getBoundingClientRect();return [r.width,r.height,r.left,r.top,innerWidth,innerHeight]", popup)
    assert bounds[0] <= bounds[4] * .97 + 1
    assert bounds[1] <= bounds[5] * .97 + 1
    assert abs(bounds[2] - (bounds[4] - bounds[0]) / 2) <= 1
    assert abs(bounds[3] - (bounds[5] - bounds[1]) / 2) <= 1
    d.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    assert not d.find_elements(By.CSS_SELECTOR, ".ttip-visible")
    assert d.execute_script("return document.activeElement===arguments[0]", cell)
    for slot, engine, capture in ((1, "sglang", "sglang_python_batch@0.5.14"), (2, "vllm", "vllm_python_batch@0.26.0")):
        choose_slot(d, slot, engine, capture)
        segments = cell.find_elements(By.CSS_SELECTOR, ".matrix-status")
        assert len(segments) == slot + 1
        widths = d.execute_script("return [...arguments[0].querySelectorAll('.matrix-status')].map(n=>n.getBoundingClientRect().width)", cell)
        assert max(widths) - min(widths) <= 1
        assert [segment.get_attribute("data-capture") for segment in segments] == selection(d)["keys"]
    cell.click()
    popup = d.find_element(By.CSS_SELECTOR, "body > .ttip-visible")
    capture_select = d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']")
    capture_select.send_keys(Keys.ARROW_DOWN)
    assert d.execute_script("return document.activeElement===arguments[0]", capture_select)
    assert selection(d)["keys"][0] == "dynamo_v1@9.2.10"
    visible = d.execute_script("return [...arguments[0].querySelectorAll('.ttip-chunks th[data-cand]:not(.col-hidden)')].map(n=>n.dataset.cand)", popup)
    assert "dynamo_v1@9.2.10" in visible and DEFAULTS[0] not in visible
    d.find_element(By.CSS_SELECTOR, "[data-slot-open='0']").send_keys(Keys.ENTER)
    picker = d.find_element(By.CSS_SELECTOR, ".comparison-picker[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value("dynamo_v1@9.2.7")
    picker.send_keys(Keys.ESCAPE)
    assert popup.is_displayed()
    assert selection(d)["keys"][0] == "dynamo_v1@9.2.7"
    popup.find_element(By.CSS_SELECTOR, ".ttip-close").click()
    assert not d.find_elements(By.CSS_SELECTOR, ".ttip-visible")


def test_unified_case_columns_have_no_repeated_vertical_rules(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    result = d.execute_script("""
      const headers = [...document.querySelectorAll('#tab-unified th.case-sub')];
      const group = headers.map(header => header.dataset.colHideGroup)
        .find(key => headers.filter(header => header.dataset.colHideGroup === key).length > 1);
      const inner = headers.find((header, index) => index > 0
        && header.dataset.colHideGroup === group && !header.classList.contains('case-group-start'));
      const boundary = headers.find(header => header.classList.contains('case-group-start')
        && header.dataset.colHideGroup !== group);
      const cells = [...document.querySelectorAll('#tab-unified tbody td.cell[data-col-hide-group]')];
      const cell = cells.find(candidate => candidate.dataset.colHideGroup === group
        && !candidate.classList.contains('case-group-start'));
      const cellStart = cells.find(candidate => candidate.classList.contains('case-group-start'));
      return {
        innerRight: getComputedStyle(inner).borderRightWidth,
        headerBoundaryLeft: getComputedStyle(boundary).borderLeftWidth,
        headerBoundaryColor: getComputedStyle(boundary).borderLeftColor,
        cellLeft: getComputedStyle(cell).borderLeftWidth,
        cellRight: getComputedStyle(cell).borderRightWidth,
        cellStartLeft: getComputedStyle(cellStart).borderLeftWidth,
        segmentShadow: getComputedStyle(cell).boxShadow
      };
    """)
    assert result == {
        "innerRight": "0px",
        "headerBoundaryLeft": "1px",
        "headerBoundaryColor": "rgb(220, 225, 231)",
        "cellLeft": "0px",
        "cellRight": "0px",
        "cellStartLeft": "0px",
        "segmentShadow": "none",
    }
    dark_color = d.execute_script("""
      const root = document.documentElement;
      const original = root.getAttribute('data-theme');
      root.setAttribute('data-theme', 'dark');
      const header = document.querySelector('#tab-unified table[data-parity-table] th.case-sub.case-group-start');
      const color = getComputedStyle(header).borderLeftColor;
      if (original === null) root.removeAttribute('data-theme');
      else root.setAttribute('data-theme', original);
      return color;
    """)
    assert dark_color == "rgb(71, 85, 105)"


def test_transposed_table_keeps_group_rows_without_vertical_case_rules(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?vertical=1")
    result = d.execute_script("""
      const cell = document.querySelector('#tab-unified .transpose-table td.cell.case-group-start');
      const groupRows = document.querySelectorAll('#tab-unified .transpose-table tr.section').length;
      const style = getComputedStyle(cell);
      return {groupRows, borderLeft: style.borderLeftWidth, borderRight: style.borderRightWidth};
    """)
    assert result["groupRows"] > 0
    assert result["borderLeft"] == result["borderRight"] == "0px"


@pytest.mark.parametrize("query,detailed", [("", True), ("?vertical=1", False), ("?vertical=1", True)])
def test_case_headings_and_cells_stay_click_only_in_all_views(matrix_driver, rendered_page, query, detailed):
    d = matrix_driver
    load(d, rendered_page, query)
    if detailed:
        d.find_element(By.CSS_SELECTOR, "[data-view-detailed]").click()
    for selector in ("td.cell[data-ttip-id]", "th[data-ttip-id]"):
        host = next(element for element in d.find_elements(By.CSS_SELECTOR, "#tab-unified " + selector) if element.is_displayed())
        d.execute_script("arguments[0].dispatchEvent(new PointerEvent('pointerover',{bubbles:true}));arguments[0].focus()", host)
        assert not d.find_elements(By.CSS_SELECTOR, ".ttip-visible")
        assert not host.find_elements(By.CSS_SELECTOR, ".ttip-built")
        host.send_keys(Keys.SPACE)
        popup = WebDriverWait(d, 10).until(lambda b: b.find_element(By.CSS_SELECTOR, "body > .ttip-visible"))
        assert popup.is_displayed()
        d.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        assert not d.find_elements(By.CSS_SELECTOR, ".ttip-visible")
        assert d.execute_script("return document.activeElement===arguments[0]", host)


def test_status_palette_and_source_blocker_are_distinct(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?slots_tab-unified=dynamo_v1%409.2.13%2Cvllm_python_batch%400.26.0%2C")
    machine_statuses = d.execute_script("""
        return [['missing_capture', 'This engine has no parser'],
                ['unsupported_family', 'No captured result'],
                ['unsupported_request_mode', 'No captured result'],
                ['source_unavailable', 'No captured result']].map(([code, prose]) => {
            const cell = {kind:'cell', cmp:{candidate:{na:1}, golden:{sig:'oracle'}},
                tooltip:{candidates:[{key:'candidate', block:{unavailable_code:code, unavailable:prose}}]}};
            return window.__conformanceOutputStatus({id:'tab-unified'}, cell, {key:'candidate'}, 'golden');
        });
    """)
    assert machine_statuses == ["missing", "unsupported", "unsupported", "blocked"]
    blocker = d.find_element(By.CSS_SELECTOR, ".status-blocked")
    missing = d.find_element(By.CSS_SELECTOR, ".status-missing")
    for theme in ("light", "dark"):
        d.execute_script("document.documentElement.dataset.theme=arguments[0]", theme)
        colors = d.execute_script("return arguments[0].map(n=>getComputedStyle(n).backgroundColor)", [blocker, missing])
        assert colors[0] != colors[1]
    choose_slot(d, 0, "dynamo", DEFAULTS[0])
    colors_by_theme = []
    for theme in ("light", "dark"):
        d.execute_script("document.documentElement.dataset.theme=arguments[0]", theme)
        colors_by_theme.append(d.execute_script("return ['pass','diverge','leak','error'].map(s=>{const n=document.querySelector('.status-'+s);return n?getComputedStyle(n).backgroundColor:null})"))
    assert colors_by_theme[0] != colors_by_theme[1]
    assert all(color is None or color != "rgba(0, 0, 0, 0)" for row in colors_by_theme for color in row)
