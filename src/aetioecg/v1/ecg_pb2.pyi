from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Sex(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SEX_UNSPECIFIED: _ClassVar[Sex]
    SEX_MALE: _ClassVar[Sex]
    SEX_FEMALE: _ClassVar[Sex]

class StatementKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STATEMENT_KIND_UNSPECIFIED: _ClassVar[StatementKind]
    STATEMENT_KIND_DIAGNOSTIC: _ClassVar[StatementKind]
    STATEMENT_KIND_FORM: _ClassVar[StatementKind]
    STATEMENT_KIND_RHYTHM: _ClassVar[StatementKind]
SEX_UNSPECIFIED: Sex
SEX_MALE: Sex
SEX_FEMALE: Sex
STATEMENT_KIND_UNSPECIFIED: StatementKind
STATEMENT_KIND_DIAGNOSTIC: StatementKind
STATEMENT_KIND_FORM: StatementKind
STATEMENT_KIND_RHYTHM: StatementKind

class ListOptionsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Statement(_message.Message):
    __slots__ = ("code", "description", "kinds")
    CODE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    KINDS_FIELD_NUMBER: _ClassVar[int]
    code: str
    description: str
    kinds: _containers.RepeatedScalarFieldContainer[StatementKind]
    def __init__(self, code: _Optional[str] = ..., description: _Optional[str] = ..., kinds: _Optional[_Iterable[_Union[StatementKind, str]]] = ...) -> None: ...

class EcgOptions(_message.Message):
    __slots__ = ("source", "statements")
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    STATEMENTS_FIELD_NUMBER: _ClassVar[int]
    source: str
    statements: _containers.RepeatedCompositeFieldContainer[Statement]
    def __init__(self, source: _Optional[str] = ..., statements: _Optional[_Iterable[_Union[Statement, _Mapping]]] = ...) -> None: ...

class EcgRequest(_message.Message):
    __slots__ = ("statements", "sex", "age", "seed")
    STATEMENTS_FIELD_NUMBER: _ClassVar[int]
    SEX_FIELD_NUMBER: _ClassVar[int]
    AGE_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    statements: _containers.RepeatedScalarFieldContainer[str]
    sex: Sex
    age: int
    seed: int
    def __init__(self, statements: _Optional[_Iterable[str]] = ..., sex: _Optional[_Union[Sex, str]] = ..., age: _Optional[int] = ..., seed: _Optional[int] = ...) -> None: ...

class Attribution(_message.Message):
    __slots__ = ("record", "citation", "license")
    RECORD_FIELD_NUMBER: _ClassVar[int]
    CITATION_FIELD_NUMBER: _ClassVar[int]
    LICENSE_FIELD_NUMBER: _ClassVar[int]
    record: str
    citation: str
    license: str
    def __init__(self, record: _Optional[str] = ..., citation: _Optional[str] = ..., license: _Optional[str] = ...) -> None: ...

class Ecg(_message.Message):
    __slots__ = ("mime_type", "image", "statements", "sex", "age", "seed", "attribution")
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    STATEMENTS_FIELD_NUMBER: _ClassVar[int]
    SEX_FIELD_NUMBER: _ClassVar[int]
    AGE_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    ATTRIBUTION_FIELD_NUMBER: _ClassVar[int]
    mime_type: str
    image: bytes
    statements: _containers.RepeatedCompositeFieldContainer[Statement]
    sex: Sex
    age: int
    seed: int
    attribution: Attribution
    def __init__(self, mime_type: _Optional[str] = ..., image: _Optional[bytes] = ..., statements: _Optional[_Iterable[_Union[Statement, _Mapping]]] = ..., sex: _Optional[_Union[Sex, str]] = ..., age: _Optional[int] = ..., seed: _Optional[int] = ..., attribution: _Optional[_Union[Attribution, _Mapping]] = ...) -> None: ...
