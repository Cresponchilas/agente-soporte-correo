"""Contratos de entrada y salida de la API (validados por Pydantic)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CorreoEntrante(BaseModel):
    remitente: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    asunto: str = Field(default="", max_length=200)
    # Tope de largo: un correo gigante dispararía el costo del prompt.
    cuerpo: str = Field(min_length=5, max_length=4000)


class DecisionHumana(BaseModel):
    accion: Literal["aprobar", "editar", "rechazar"]
    texto: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def editar_requiere_texto(self) -> "DecisionHumana":
        if self.accion == "editar" and not (self.texto and self.texto.strip()):
            raise ValueError("Para editar hay que enviar el texto nuevo")
        return self


class CasoDePrueba(BaseModel):
    id: str
    entrada: CorreoEntrante
    esperado: dict


class Salud(BaseModel):
    estado: Literal["ok"]
    persistencia: Literal["postgres", "memoria"]
    modelo: str
