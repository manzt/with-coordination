from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from inline_snapshot import snapshot
from ipywidgets import FloatSlider

from with_coordination import Coordination

if TYPE_CHECKING:
    import pathlib


@pytest.fixture
def coordination_path(tmp_path: pathlib.Path):
    with open(tmp_path / "config.json", "w") as f:
        f.write("""
        {
          "key": 1,
          "coordinationSpace": { "sliderValue": { "A": 0.5, "B": 0.75 } },
          "viewCoordination": {
            "slider1": { "coordinationScopes": { "sliderValue": "A" } },
            "slider2": { "coordinationScopes": { "sliderValue": "B" } },
            "slider3": { "coordinationScopes": { "sliderValue": "B" } }
          }
        }
        """)
    return tmp_path / "config.json"


def test_coordination_json_without_ids():
    slider1 = FloatSlider()
    slider2 = FloatSlider()
    slider3 = FloatSlider()

    with Coordination() as c:
        with c.type("sliderValue") as t:
            with t.scope("A", 10) as s:
                s.view(slider1, alias="value")

            with t.scope("B", 4.0) as s:
                s.view(slider2, alias="value")
                s.view(slider3, alias="value")

    assert c.to_json() == snapshot(
        '{"coordinationSpace":{"sliderValue":{"A":10,"B":4.0}},"viewCoordination":{"view_0":{"coordinationScopes":{"sliderValue":"A"}},"view_1":{"coordinationScopes":{"sliderValue":"B"}},"view_2":{"coordinationScopes":{"sliderValue":"B"}}}}'
    )


def test_widgets_coordination():
    slider1 = FloatSlider()
    slider2 = FloatSlider()
    slider3 = FloatSlider()

    with Coordination() as c:
        with c.type("sliderValue") as t:
            with t.scope("A", 10) as s:
                s.view(slider1, alias="value")

            with t.scope("B", 4.0) as s:
                s.view(slider2, alias="value")
                s.view(slider3, alias="value")

    assert slider1.value == 10
    assert slider2.value == 4.0
    assert slider3.value == 4.0

    slider1.value = 20
    assert slider1.value == 20
    assert slider2.value == 4.0
    assert slider3.value == 4.0

    slider2.value = 8.0
    assert slider1.value == 20
    assert slider2.value == 8.0
    assert slider3.value == 8.0


def test_coordination_from_file(coordination_path: pathlib.Path):
    with Coordination(coordination_path) as c:
        assert c.to_json() == snapshot(
            '{"coordinationSpace":{"sliderValue":{"A":0.5,"B":0.75}},"viewCoordination":{"slider1":{"coordinationScopes":{"sliderValue":"A"}},"slider2":{"coordinationScopes":{"sliderValue":"B"}},"slider3":{"coordinationScopes":{"sliderValue":"B"}}}}'
        )


def test_coordination_builder_fails_without_widget_or_id():
    with Coordination() as c:
        with c.type("foo") as t:
            with t.scope("bar", 10) as s:
                with pytest.raises(ValueError):
                    s.view(alias="value")


def test_simple_coordination_builder():
    with Coordination() as c:
        with c.type("foo") as t:
            with t.scope("bar", 10) as s:
                s.view(id="view1", alias="value")
                s.view(id="view2", alias="value")
            with t.scope("baz", 20) as s:
                s.view(id="view3", alias="value")

    assert c.to_json() == snapshot(
        '{"coordinationSpace":{"foo":{"bar":10,"baz":20}},"viewCoordination":{"view1":{"coordinationScopes":{"foo":"bar"}},"view2":{"coordinationScopes":{"foo":"bar"}},"view3":{"coordinationScopes":{"foo":"baz"}}}}'
    )


def test_new_coordination_clears_previous():
    slider1 = FloatSlider()
    slider2 = FloatSlider()
    slider3 = FloatSlider()

    with Coordination() as c:
        with c.type("sliderValue") as t:
            with t.scope("A", 10) as s:
                s.view(slider1, alias="value")

            with t.scope("B", 4.0) as s:
                s.view(slider2, alias="value")
                s.view(slider3, alias="value")

    slider2.value = 8.0
    assert slider1.value == 10
    assert slider2.value == 8.0
    assert slider3.value == 8.0

    with Coordination() as c:
        with c.type("sliderValue") as t:
            with t.scope("A", 20) as s:
                s.view(slider1, alias="value")
                s.view(slider2, alias="value")

            with t.scope("B", 5.0) as s:
                s.view(slider3, alias="value")

    slider1.value = 30
    assert slider1.value == 30
    assert slider2.value == 30
    assert slider3.value == 5.0


def test_add_widgets_to_existing_coordination(coordination_path: pathlib.Path):
    slider1 = FloatSlider()
    slider2 = FloatSlider()
    slider3 = FloatSlider()

    with Coordination(coordination_path) as c:
        c.use_widget(slider1, view_id="slider1", aliases={"value": "sliderValue"})
        c.use_widget(slider2, view_id="slider2", aliases={"value": "sliderValue"})
        c.use_widget(slider3, view_id="slider3", aliases={"value": "sliderValue"})

    assert slider1.value == 0.5
    assert slider2.value == 0.75
    assert slider3.value == 0.75

    slider1.value = 0.6
    assert slider1.value == 0.6
    assert slider2.value == 0.75
    assert slider3.value == 0.75

    slider2.value = 0.8
    assert slider1.value == 0.6
    assert slider2.value == 0.8
    assert slider3.value == 0.8


def test_jslink_for_type():
    slider1 = FloatSlider()
    slider2 = FloatSlider()

    with patch("ipywidgets.jslink") as jslink:
        with Coordination() as c:
            with c.type("sliderValue", jslink=True) as t:
                with t.scope("A", 10) as s:
                    s.view(slider1, alias="value")
                    s.view(slider2, alias="value")

        assert jslink.call_count == 1


def test_jslink_for_scope():
    slider1 = FloatSlider()
    slider2 = FloatSlider()

    slider3 = FloatSlider()
    slider4 = FloatSlider()

    with patch("ipywidgets.jslink") as jslink:
        with Coordination() as c:
            with c.type("sliderValue") as t:
                with t.scope("A", 10, jslink=True) as s:
                    s.view(slider1, alias="value")
                    s.view(slider2, alias="value")

                with t.scope("B", 4.0) as s:
                    s.view(slider3, alias="value")
                    s.view(slider4, alias="value")

        assert jslink.call_count == 1
