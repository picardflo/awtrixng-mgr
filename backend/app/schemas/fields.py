"""Declarative form schema.

This is what lets the frontend hold **no hard-coded form** for any connector
(§10). A connector describes its fields; `SchemaForm` renders them. Adding a
connector therefore adds no frontend file.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

FieldType = Literal[
    "text",
    "number",
    "boolean",
    "select",
    "multiselect",
    #: Options fetched from the connector through discover().
    "remote_select",
    #: Same, but several may be picked. Stores a list of values.
    "remote_multiselect",
    #: Write-only. Never echoed back by the API.
    "secret",
    "url",
    "duration",
    "color",
    "template",
    #: A geographic place. The stored value is
    #: {"name": str, "latitude": float, "longitude": float}, chosen through a
    #: search rather than typed: nobody knows their own latitude.
    "place",
    #: One of the configured AWTRIX displays, stored as its id. Chosen from a
    #: list the frontend already holds, so it needs no discover() call — which
    #: matters, since the choice happens before the connector exists.
    "device",
]
#: An "icon" type was sketched here first and dropped: icons belong to the
#: display options, not to a connector's configuration.


class Option(BaseModel):
    value: str
    label: str
    #: Free-form extra shown next to the label, e.g. a host name.
    hint: str | None = None


class FormField(BaseModel):
    name: str
    label: str
    type: FieldType = "text"
    required: bool = False
    default: Any = None
    help: str | None = None
    placeholder: str | None = None

    #: select / multiselect
    options: list[Option] | None = None
    #: remote_select, remote_multiselect: which discover() source feeds it.
    source: str | None = None
    #: remote_select: re-fetch options when these fields change.
    depends_on: list[str] | None = None

    #: number / duration bounds.
    minimum: float | None = Field(default=None, alias="min")
    maximum: float | None = Field(default=None, alias="max")
    unit: str | None = None

    model_config = {"populate_by_name": True}


class Variable(BaseModel):
    """One key of WidgetData.values, documented for the template editor.

    Without this the user has to guess what `{{ … }}` accepts.
    """

    name: str
    label: str
    example: str | None = None
