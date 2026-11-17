"""Sistemas externos simulados. En producción cada función llamaría a una API real."""

BANDEJA_DE_SALIDA: list[dict] = []  # para poder inspeccionar en la demo qué se "envió"


def enviar_correo(destinatario: str, asunto: str, cuerpo: str) -> None:
    BANDEJA_DE_SALIDA.append({"para": destinatario, "asunto": asunto, "cuerpo": cuerpo})
