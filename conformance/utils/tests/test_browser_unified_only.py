# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from urllib.parse import quote

import pytest

pytest.importorskip("selenium")
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from conformance.utils.tests.test_browser_comparison_layout import DEFAULTS, choose_slot, load, matrix_driver, selection
from conformance.utils.src.validate_conformance_status import load_model, validate_unified_only_report


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
def test_removed_tab_links_open_the_unified_report_without_a_tab_button(matrix_driver, rendered_page, removed):
    d = matrix_driver
    load(d, rendered_page, "?tab=" + removed)
    assert d.execute_script("return [...document.querySelectorAll('.tab-panel')].map(node=>node.id)") == ["tab-unified"]
    assert not d.find_elements(By.CSS_SELECTOR, ".tab-button")
    assert selection(d)["keys"] == DEFAULTS


def test_none_slots_and_duplicate_selections(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=" + quote(",,"))
    assert selection(d) == {"keys": [], "reference": None}
    assert not d.find_elements(By.CSS_SELECTOR, "#tab-unified td.cell.cmp-leak")
    choose_slot(d, 0, "dynamo", "dynamo_v1@9.2.10")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    assert d.find_elements(By.CSS_SELECTOR, "#tab-unified td.cell.cmp-leak")
    picker = choose_slot(d, 1, "dynamo", close=False)
    assert picker.find_element(By.CSS_SELECTOR, "option[value='dynamo_v1@9.2.10']").get_attribute("disabled")
    Select(picker.find_element(By.CSS_SELECTOR, "[data-picker-engine]")).select_by_value("none")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.10"]
    picker.find_element(By.CSS_SELECTOR, "[data-picker-close]").click()
    d.find_element(By.CSS_SELECTOR, "[data-reset]").click()
    WebDriverWait(d, 10).until(lambda browser: selection(browser)["keys"] == DEFAULTS)


def test_unavailable_capture_is_explained_and_older_links_can_select_it(matrix_driver, rendered_page):
    d = matrix_driver
    load(d, rendered_page)
    d.find_element(By.CSS_SELECTOR, ".capture-slot [data-slot-picker='0']").click()
    option = d.find_element(By.CSS_SELECTOR, ".capture-picker [data-picker-capture] option[value='dynamo_v1@9.2.13']")
    assert option.get_attribute("disabled")
    assert "no captured results" in option.text

    load(d, rendered_page, "?tab=tab-unified&slots_tab-unified=dynamo_v1%409.2.13%2C%2C")
    assert selection(d)["keys"] == ["dynamo_v1@9.2.13"]
    assert d.find_elements(By.CSS_SELECTOR, "#tab-unified td.cell.cmp-na")
