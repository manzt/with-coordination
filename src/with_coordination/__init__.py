import pathlib
import typing
import dataclasses
import weakref

import ipywidgets
import msgspec

__all__ = ["Coordination"]


class ViewCoordinationConfig(msgspec.Struct, rename="camel"):
    coordination_scopes: dict[str, str] = {}


class CoordinationConfig(msgspec.Struct, rename="camel"):
    coordination_space: dict[str, dict[str, typing.Any]] = {}
    view_coordination: dict[str, ViewCoordinationConfig] = {}


class CoordinationScope(msgspec.Struct):
    type: str
    name: str
    value: typing.Any


class View(msgspec.Struct):
    widget: ipywidgets.Widget
    aliases: dict[str, str] = {}

    def alias(self, **kwargs):
        self.aliases.update({v: k for k, v in kwargs.items()})
        return self


def _resolve_scope_and_link(
    config: CoordinationConfig, scope: CoordinationScope, views: dict[str, View]
):
    resolved: list[tuple[ipywidgets.Widget, str]] = []
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
        resolved.append((view.widget, field))

    if len(resolved) == 0:
        return []

    links: list[ipywidgets.link] = []

    # link all the resolved scopes together
    # TODO: there probably is a better way to do this.
    # Ideally, on the Python side we have one "Model" for the scope
    # and on the JS side the same. But maybe for now this is fine...
    v1, f1 = resolved[0]
    for view, field in resolved[1:]:
        link = ipywidgets.link((v1, f1), (view, field))
        links.append(link)
    return links


def _resolve_config(config_or_path: pathlib.Path | dict):
    if isinstance(config_or_path, dict):
        config = msgspec.convert(config_or_path, type=CoordinationConfig)
    else:
        contents = pathlib.Path(config_or_path).read_text(encoding="utf-8")
        config = msgspec.json.decode(contents, type=CoordinationConfig)
    return config


WIDGET_COORDINATION_IDS = weakref.WeakKeyDictionary()
# TODO: We should try to use weakrefs here as well
LINKS = {}


class Coordination:
    """Register and coordinate Jupyter widgets with a declarative API.

    This class is used to coordinate Jupyter widgets with a declarative API.
    It allows to define a coordination space and link the widgets together
    using the use-coordination specification.
    """

    def __init__(self, config: pathlib.Path | dict | None = None):
        self._config = (
            CoordinationConfig() if config is None else _resolve_config(config)
        )
        self._views: dict[str, View] = {}
        self._unknown_view_id = 0

    def use_widget(self, widget: ipywidgets.Widget, view_id: str, aliases: dict):
        self._views[view_id] = View(widget).alias(**aliases)

    def type(self, type: str):
        return CoordinationTypeContext(_coord=self, _type=type)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        if len(self._views) == 0:
            return

        # widgets can only have one coordination at a time
        # so we need to remove the old links before creating new ones
        coordination_ids = set(
            WIDGET_COORDINATION_IDS.get(view.widget) for view in self._views.values()
        )
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

    def to_json(self) -> bytes:
        return msgspec.json.encode(self._config)


@dataclasses.dataclass
class CoordinationTypeContext:
    _coord: Coordination
    _type: str

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def scope(self, name: str, value: typing.Any):
        self._coord._config.coordination_space[self._type] = (
            self._coord._config.coordination_space.get(self._type, {})
        )
        self._coord._config.coordination_space[self._type][name] = value
        return CoordinationScopeContext(
            _cood=self._coord, _type=self._type, _name=name, _value=value
        )


T = typing.TypeVar("T")


@dataclasses.dataclass
class CoordinationScopeContext(typing.Generic[T]):
    _cood: Coordination
    _type: str
    _name: str
    _value: T

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def view(
        self,
        widget: ipywidgets.Widget | None,
        id: str | None = None,
        alias: str | None = None,
    ):
        if widget is None and id is None:
            raise ValueError("Either widget or id must be provided")

        if id is None:
            # Check if we have a for this widget already
            for view_id, view in self._cood._views.items():
                if view.widget == widget:
                    id = view_id
                    break
            else:
                # If not, create a new one
                id = f"view_{self._cood._unknown_view_id}"
                self._cood._unknown_view_id += 1

        # write to the view coordination config
        self._cood._config.view_coordination[id] = (
            self._cood._config.view_coordination.get(id, ViewCoordinationConfig())
        )
        self._cood._config.view_coordination[id].coordination_scopes[self._type] = (
            self._name
        )

        if widget is None:
            return

        # register the widget view
        self._cood._views[id] = self._cood._views.get(id, View(widget))
        if alias is not None:
            self._cood._views[id].alias(**{alias: self._type})
