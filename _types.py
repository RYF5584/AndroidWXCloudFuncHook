# coding: utf-8
# @Author: Ruan
# coding:utf-8
from pydantic import BaseModel, model_validator
from typing import *
from enum import Enum


class JsSendType(Enum):
    Request = 1
    Response = 2
    Other = 3


class Request(BaseModel):
    api_name: str
    data: Any


class Response(BaseModel):
    data: Any


class JsSendRequest(BaseModel):
    type: JsSendType
    data: Union[Request, Response, Any]

    @model_validator(mode='before')
    def validate_and_serialize_data(cls, values):
        type_ = values.get('type')
        data = values.get('data')
        if type_ == JsSendType.Request:
            values['data'] = Request.model_validate(data)
        elif type_ == JsSendType.Response:
            values['data'] = Response.model_validate(data)
        elif type_ == JsSendType.Other:
            values['data'] = data
        return values
