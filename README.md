# with-coordination

declarative coordinated multiple views for Jupyter Widgets

```sh
pip install with-coordination
```

## usage

```python
import ipywidgets

# create a set of widgets
slider1 = ipywidgets.FloatSlider(description='Slider 1')
slider2 = ipywidgets.FloatSlider(description='Slider 2')
slider3 = ipywidgets.FloatSlider(description='Slider 3')

# prepare an output area with arrangement of widgets
ipywidgets.VBox([slider1, slider2, slider3])
```

```python
from with_coordination import Coordination

# create a coordination context
with Coordination() as c:

  # define a coordination type
  with c.type("sliderValue") as t:

    # add a scope with a set of widgets
    with t.scope("A", 10) as s:
      # alias maps the widget prop to the coordination type if they are different
      s.view(slider1, alias="value")

    with t.scope("B", 4.0) as s:
      s.view(slider2, alias="value")
      s.view(slider3, alias="value")


  # get the coordination configuration as json
  print(c.to_json()) # b'{"coordinationSpace":{"sliderValue":{"A":10,"B":4.0}},"viewCoordination":{"view_0": ...'
```

Alternatively, you can use use an existing configuration to create a coordination context.

```python
with open("config.json", "w") as f:
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

with Coordination("config.json") as c:
    c.use_widget(slider1, view_id="slider1", aliases={"value": "sliderValue"})
    c.use_widget(slider2, view_id="slider2", aliases={"value": "sliderValue"})
    c.use_widget(slider3, view_id="slider3", aliases={"value": "sliderValue"})
```

## why

Managing coordinated multiple views is a complex task. This library provides an
ergonomic and declarative API to specify how widgets traits should be
coordinated.

**with-coordination** is based on the declarative JSON coordination
specification from
[`use-coordination`](https://github.com/keller-mark/use-coordination) and is
designed to work with [anywidget](https://anywidget.dev).

## development

this project is managed using [rye](https://rye-up.com/).

```py
rye run jupyter lab
```

rye manages testing, linting, and formatting.

```sh
rye test
rye lint
rye format
```

alternatively you can create a virtual environment and use an development installation. You will need to install `jupyterlab`.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install jupyterlab
jupyter lab
```
