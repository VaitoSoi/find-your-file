from typing import Any

from pydantic import BaseModel


def _wrap(content: dict[str, Any]) -> dict[str, Any]:
    return {"content": {"application/json": content}}


def MESSAGE_OK() -> dict[str, Any]:
    return _wrap(
        {
            "schema": {
                "type": "object",
                "properties": {"message": {"type": "string", "default": "ok"}},
            },
            "example": {"message": "ok"},
        }
    )


def MESSAGE_UPDATE(
    field: str, model: BaseModel | None = None, ref: str | None = None
) -> dict[str, Any]:
    ref = (
        "#/components/schemas/" + ref
        if ref and not ref.startswith("#/components/schemas/")
        else ref
    )

    return _wrap(
        {
            "schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "default": "updated"},
                    **(
                        {field: model.model_json_schema()}
                        if model
                        else {field: {"$ref": ref}}
                    ),
                },
            }
        }
    )


def HTTP_EXECEPTION_MESSAGE(
    message: str | list[str] | None = None,
    extend: tuple[dict[str, Any], dict[str, Any]] = ({}, {}),
) -> dict[str, Any]:
    return _wrap(
        {
            "schema": {
                "type": "object",
                "properties": {
                    "detail": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                **(
                                    {"enum": message}
                                    if isinstance(message, list)
                                    else {}
                                ),
                            },
                            **extend[0],
                        },
                    },
                },
            },
            **(
                {"example": {"detail": {"message": message, **extend[1]}}}
                if isinstance(message, str)
                else {}
            ),
        }
    )


def USER_NOT_FOUND():
    return {
        404: HTTP_EXECEPTION_MESSAGE(
            "user not found", ({"id": {"type": "string"}}, {"id": "string"})
        )
    }
