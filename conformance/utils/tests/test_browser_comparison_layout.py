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
    picker = driver.find_element(By.CSS_SELECTOR, ".capture-picker[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value(engine)
    if engine != "none" and capture is not None:
        Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value(capture)
    if close and picker.is_displayed():
        picker.send_keys(Keys.ESCAPE)
    return picker


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
    assert [element.get_attribute("value") for element in d.find_elements(By.CSS_SELECTOR, ".capture-slot [data-slot-capture]")] == [DEFAULTS[0], "", ""]
    assert not d.find_elements(By.CSS_SELECTOR, ".capture-slot [data-slot-capture='0'] option[value='']")
    assert len(d.find_elements(By.CSS_SELECTOR, "[data-slot-capture='1'] option[value=''],[data-slot-capture='2'] option[value='']")) == 2
    assert [element.text for element in d.find_elements(By.CSS_SELECTOR, ".capture-slot [data-slot-engine]")] == ["Dynamo", "SGLang", "vLLM"]
    Select(d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']")).select_by_value("dynamo_v1@9.2.10")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    assert not d.find_elements(By.CSS_SELECTOR, ".capture-picker[open]")
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
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value("")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    assert d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-engine='1']").text.upper() == "DYNAMO"


def test_primary_slot_cannot_be_empty_and_engine_change_selects_a_version(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=%2C%2C")
    assert selection(d)["keys"] == DEFAULTS
    d.find_element(By.CSS_SELECTOR, "[data-slot-open='0']").click()
    picker = d.find_element(By.CSS_SELECTOR, ".capture-picker[open]")
    assert not picker.find_elements(By.CSS_SELECTOR, "[data-picker-capture] option[value='']")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("sglang")
    selected = selection(d)["keys"]
    assert len(selected) == 1 and selected[0].startswith("sglang_python")
    assert d.find_element(By.CSS_SELECTOR, "[data-slot-capture='0']").get_attribute("value") == selected[0]


def test_engine_badges_open_live_picker_without_a_done_button(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    for slot, engine in enumerate(("dynamo", "sglang", "vllm")):
        d.find_element(By.CSS_SELECTOR, f"[data-slot-open='{slot}']").click()
        picker = d.find_element(By.CSS_SELECTOR, ".capture-picker[open]")
        assert picker.find_element(By.TAG_NAME, "h2").text == f"Comparison slot {slot + 1}"
        assert not picker.find_elements(By.CSS_SELECTOR, "button")
        assert Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).first_selected_option.get_attribute("value") == engine
        assert Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).first_selected_option.get_attribute("value") == (DEFAULT_SLOTS[slot] or "")
        picker.send_keys(Keys.ESCAPE)
    assert selection(d)["keys"] == DEFAULTS

    d.find_element(By.CSS_SELECTOR, "[data-slot-open='1']").click()
    picker = d.find_element(By.CSS_SELECTOR, ".capture-picker[open]")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("vllm")
    assert selection(d)["keys"] == DEFAULTS
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-capture]")).select_by_value("vllm_python_batch@0.26.0")
    assert selection(d)["keys"] == [*DEFAULTS, "vllm_python_batch@0.26.0"]
    assert picker.is_displayed()
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
    picker = d.find_element(By.CSS_SELECTOR, ".capture-picker[open]")
    geometry = d.execute_script("const a=arguments[0].getBoundingClientRect(),p=arguments[1].getBoundingClientRect();return {left:p.left,right:p.right,top:p.top,bottom:p.bottom,w:innerWidth,h:innerHeight,gap:Math.min(Math.abs(a.right-p.left),Math.abs(p.right-a.left))}", trigger, picker)
    assert geometry["left"] >= 0 and geometry["top"] >= 0
    assert geometry["right"] <= geometry["w"] and geometry["bottom"] <= geometry["h"]
    assert geometry["gap"] <= 9
    picker.send_keys(Keys.ESCAPE)
    assert d.execute_script("return document.activeElement.dataset.slotOpen") == "2"

    trigger.click()
    picker = d.find_element(By.CSS_SELECTOR, ".capture-picker[open]")
    d.execute_script("arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true}))", picker)
    assert not d.find_elements(By.CSS_SELECTOR, ".capture-picker[open]")
    assert d.execute_script("return document.activeElement.dataset.slotOpen") == "2"
