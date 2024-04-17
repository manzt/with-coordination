"""A module for declarative coordination of Jupyter Widgets.

This module provides a class to coordinate Jupyter widgets with the declarative,
use-coordination specification.

Usage:

```python
import ipywidgets
from with_coordination import Coordination

slider1 = ipywidgets.FloatSlider(description="Slider 1")
slider2 = ipywidgets.FloatSlider(description="Slider 2")
slider3 = ipywidgets.FloatSlider(description="Slider 3")

with Coordination() as c:
    with c.type("sliderValue") as t:
        with t.scope("A", 10) as s:
            s.view(slider1, alias="value")

        with t.scope("B", 4.0) as s:
            s.view(slider2, alias="value")
            s.view(slider3, alias="value")

# The sliders are now linked together
ipywidgets.VBox([slider1, slider2, slider3])
```

Alternatively, you can also load the configuration from a file and apply
it to the widgets:

```python
with Coordination("config.json") as c:
    c.use_widget(slider1, view_id"slider1", aliases={"value": "sliderValue"})
    c.use_widget(slider2, view_id"slider2", aliases={"value": "sliderValue"})
    c.use_widget(slider3, view_id"slider3", aliases={"value": "sliderValue"})
```
"""

import pathlib
import typing
import weakref

import ipywidgets
import msgspec

__all__ = ["Coordination"]


class ViewCoordinationConfig(msgspec.Struct, rename="camel"):
    coordination_scopes: typing.Dict[str, str] = {}


class CoordinationConfig(msgspec.Struct, rename="camel"):
    """The use-coordination configuration."""

    coordination_space: typing.Dict[str, typing.Dict[str, typing.Any]] = {}
    view_coordination: typing.Dict[str, ViewCoordinationConfig] = {}


class CoordinationScope(msgspec.Struct):
    type: str
    name: str
    value: typing.Any


class View(msgspec.Struct):
    widget: ipywidgets.Widget
    aliases: typing.Dict[str, str] = {}
    jslinks: typing.Set[str] = set()

    def alias(self, **kwargs):
        self.aliases.update({v: k for k, v in kwargs.items()})
        return self

    def jslink(self, field: str):
        self.jslinks.add(field)
        return self


def _resolve_scope_and_link(
    config: CoordinationConfig, scope: CoordinationScope, views: typing.Dict[str, View]
):
    resolved: list[tuple[ipywidgets.Widget, str, bool]] = []
    for view_name, view_config in config.view_coordination.items():
        view_scopes = view_config.coordination_scopes
        if scope.type not in view_scopes or scope.name not in view_scopes[scope.type]:
            continue

        # get the coresponding view
        view = views[view_name]
        # resolve the alias, fallback to scope name
        field = view.aliases.get(scope.type, scope.type)
        # set the current value to the scope
        setattr(view.widget, field, scope.value)
        # keep the resolved so we can link them together
        resolved.append((view.widget, field, field in view.jslinks))

    if len(resolved) == 0:
        return []

    links: list[ipywidgets.link] = []

    # link all the resolved scopes together
    # TODO: there probably is a better way to do this.
    # Ideally, on the Python side we have one "Model" for the scope
    # and on the JS side the same. But maybe for now this is fine...
    v1, f1, should_jslink1 = resolved[0]
    for view, field, should_jslink in resolved[1:]:
        if should_jslink1 and should_jslink:
            link = ipywidgets.jslink((v1, f1), (view, field))
        else:
            link = ipywidgets.link((v1, f1), (view, field))
        links.append(link)
    return links


WIDGET_COORDINATION_IDS: "weakref.WeakKeyDictionary[ipywidgets.Widget, int]" = (
    weakref.WeakKeyDictionary()
)
# TODO: We should try to use weakrefs here as well
LINKS = {}


class Coordination:
    """Register and coordinate Jupyter widgets with a declarative API.

    This class is used to coordinate Jupyter widgets with a declarative API.
    It allows to define a coordination space and link the widgets together
    using the use-coordination specification.
    """

    def __init__(self, config: typing.Union[pathlib.Path, dict, None] = None) -> None:
        if config is None:
            self._config = CoordinationConfig()
        elif isinstance(config, dict):
            self._config = msgspec.convert(config, type=CoordinationConfig)
        else:
            contents = pathlib.Path(config).read_text(encoding="utf-8")
            self._config = msgspec.json.decode(contents, type=CoordinationConfig)
        self._views: typing.Dict[str, View] = {}
        self._unknown_view_id = 0

    def use_widget(
        self,
        widget: ipywidgets.Widget,
        view_id: str,
        aliases: typing.Union[typing.Dict[str, str], None] = None,
        jslinks: typing.Union[typing.Set[str], None] = None,
    ) -> None:
        """Register a widget as a view in the coordination space.

        Parameters
        ----------
        widget : ipywidgets.Widget
            The widget to be registered.
        view_id : str
            The view id of the widget.
        aliases : dict (optional)
            A dictionary mapping widget fields to coordination types in the
            coordination space.
        jslinks : set (optional)
            A set of widget fields that should be linked using ipywidgets.jslink.
        """
        self._views[view_id] = View(
            widget,
            jslinks=jslinks or set(),
            aliases={v: k for k, v in (aliases or {}).items()},
        )

    def type(self, type: str, jslink: bool = False) -> "CoordinationTypeContext":
        """Enter the coordination type context."""
        return CoordinationTypeContext(coordination=self, type=type, jslink=jslink)

    def __enter__(self) -> "Coordination":
        """Enter the coordination context."""
        return self

    def __exit__(self, *_: object) -> None:
        """Exit the coordination context.

        This method is called when the context manager is exited. It will resolve the
        coordination configuration and link any registered widgets together using the
        coordination space.
        """
        if len(self._views) == 0:
            return

        # widgets can only have one coordination at a time
        # so we need to remove the old links before creating new ones
        coordination_ids = {
            WIDGET_COORDINATION_IDS.get(view.widget) for view in self._views.values()
        }
        for coordination_id in coordination_ids:
            if LINKS.get(coordination_id) is not None:
                for link in LINKS[coordination_id]:
                    link.unlink()
                del LINKS[coordination_id]

        all_links = []
        for type_, scopes in self._config.coordination_space.items():
            for scope_name, scope_value in scopes.items():
                scope = CoordinationScope(
                    type=type_, name=scope_name, value=scope_value
                )
                links = _resolve_scope_and_link(self._config, scope, self._views)
                all_links.extend(links)
        LINKS[id(self)] = all_links
        for view in self._views.values():
            WIDGET_COORDINATION_IDS[view.widget] = id(self)

    def to_json(self) -> str:
        """Serialize the coordination configuration to use-coordination JSON format."""
        return msgspec.json.encode(self._config).decode("utf-8")


T = typing.TypeVar("T")


class CoordinationTypeContext:
    def __init__(self, coordination: Coordination, type: str, jslink: bool = False):
        self._coord = coordination
        self._type = type
        self._jslink = jslink

    def __enter__(self):
        """Enter the coordination type context."""
        return self

    def __exit__(self, *_: object):
        """Exit the coordination type context."""
        pass

    def scope(
        self, name: str, value: T, jslink: bool = False
    ) -> "CoordinationScopeContext[T]":
        """Enter the coordination scope context.

        Parameters
        ----------
        name : str
            The name of the coordination scope.
        value : T
            The value of the coordination scope.
        jslink : bool
            Whether to use ipywidgets.jslink when linking views for this scope.

        Returns
        -------
        CoordinationScopeContext
            The coordination scope context.
        """
        self._coord._config.coordination_space[self._type] = (
            self._coord._config.coordination_space.get(self._type, {})
        )
        self._coord._config.coordination_space[self._type][name] = value
        return CoordinationScopeContext(
            coordination=self._coord,
            type=self._type,
            name=name,
            value=value,
            jslink=jslink or self._jslink,
        )


class CoordinationScopeContext(typing.Generic[T]):
    def __init__(
        self,
        coordination: Coordination,
        type: str,
        name: str,
        value: T,
        jslink: bool,
    ):
        self._coord = coordination
        self._type = type
        self._name = name
        self._value = value
        self._jslink = jslink

    def __enter__(self):
        """Enter the coordination scope context."""
        return self

    def __exit__(self, *_: object):
        """Exit the coordination scope context."""
        pass

    def view(
        self,
        widget: typing.Union[ipywidgets.Widget, None] = None,
        id: typing.Union[str, None] = None,
        alias: typing.Union[str, None] = None,
        jslink: bool = False,
    ):
        """Register a widget as a view in the coordination space.

        Parameters
        ----------
        widget : ipywidgets.Widget
            The widget to be registered.
        id : str
            The view id of the widget.
        alias : str
            The alias of the widget field in the coordination space.
        jslink : bool
            Whether to use ipywidgets.jslink to link this view this scope.

        Raises
        ------
        ValueError
            If neither widget nor id is provided.

        Notes
        -----
        If only the widget is provided, the view id will be generated automatically in
        the form of `view_{int}`.
        """
        if widget is None and id is None:
            raise ValueError("Either widget or id must be provided")

        view_id = id

        if view_id is None:
            # Check if we have a for this widget already
            for vid, view in self._coord._views.items():
                if view.widget == widget:
                    view_id = vid
                    break
            else:
                # If not, create a new one
                view_id = f"view_{self._coord._unknown_view_id}"
                self._coord._unknown_view_id += 1

        # write to the view coordination config
        self._coord._config.view_coordination[view_id] = (
            self._coord._config.view_coordination.get(view_id, ViewCoordinationConfig())
        )
        self._coord._config.view_coordination[view_id].coordination_scopes[
            self._type
        ] = self._name

        if widget is None:
            return

        # register the widget view
        self._coord._views[view_id] = self._coord._views.get(view_id, View(widget))

        if alias is not None:
            self._coord._views[view_id].alias(**{alias: self._type})

        if jslink or self._jslink:
            # tag the widget for jslinking later
            self._coord._views[view_id].jslink(alias or self._type)
