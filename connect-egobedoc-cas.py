#!/usr/bin/env python
"""
Conector base para eGOB/e-Bedoc protegido por CAS.

Uso recomendado:

1. Inspeccionar el flujo de autenticacion sin credenciales:
   python connect-egobedoc-cas.py inspect

2. Iniciar sesion y descargar la bandeja del ciudadano:
   python connect-egobedoc-cas.py login --username USUARIO --password CLAVE --save-html outputs/passig_citizen.html

3. Probar otra ruta autenticada:
   python connect-egobedoc-cas.py login --username USUARIO --password CLAVE --path /my/passig_citizen

Notas:
- Este script esta pensado para ejecutarse en backend o desde una tarea automatizada, no desde el frontend.
- El portal usa CAS con token dinamico "execution", por eso el login requiere primero una peticion GET y luego un POST.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
import urllib3


DEFAULT_ORIGIN = "https://egobedoc.gadmriobamba.gob.ec:8081/my/passig_citizen"
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class InputField:
    name: str
    input_type: str
    value: str


@dataclass
class LoginForm:
    action: str
    method: str = "post"
    inputs: list[InputField] = field(default_factory=list)

    def to_payload(self, username: str, password: str) -> dict[str, str]:
        payload: dict[str, str] = {}
        for item in self.inputs:
            if item.name:
                payload[item.name] = item.value
        payload["username"] = username
        payload["password"] = password
        payload.setdefault("_eventId", "submit")
        payload.setdefault("geolocation", "")
        return payload


class CasLoginParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[LoginForm] = []
        self._current_form: LoginForm | None = None
        self._inside_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "form":
            action = attr_map.get("action", "")
            method = attr_map.get("method", "post").lower()
            self._current_form = LoginForm(action=action, method=method)
            self._inside_form = True
            self.forms.append(self._current_form)
            return

        if tag == "input" and self._inside_form and self._current_form is not None:
            self._current_form.inputs.append(
                InputField(
                    name=attr_map.get("name", ""),
                    input_type=attr_map.get("type", "text"),
                    value=attr_map.get("value", ""),
                )
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._inside_form = False
            self._current_form = None


class EgoBedocCasClient:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, verify: bool = True) -> None:
        self.timeout = timeout
        self.verify = verify
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.session.verify = verify
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def fetch_entrypoint(self, origin_url: str) -> requests.Response:
        return self.session.get(origin_url, allow_redirects=True, timeout=self.timeout)

    def inspect_login(self, origin_url: str) -> dict[str, object]:
        response = self.fetch_entrypoint(origin_url)
        form = self.extract_login_form(response.text, response.url)
        return {
            "origin_url": origin_url,
            "final_url": response.url,
            "status_code": response.status_code,
            "is_cas_login": self.is_cas_login_page(response.url, response.text),
            "form_action": form.action if form else None,
            "form_method": form.method if form else None,
            "form_input_names": [item.name for item in form.inputs] if form else [],
            "cookie_names": sorted(self.session.cookies.get_dict().keys()),
            "redirect_chain": [item.url for item in response.history] + [response.url],
            "candidate_urls": self.extract_candidate_urls(response.text, response.url),
        }

    def login(self, origin_url: str, username: str, password: str) -> requests.Response:
        landing = self.fetch_entrypoint(origin_url)
        if not self.is_cas_login_page(landing.url, landing.text):
            return landing

        form = self.extract_login_form(landing.text, landing.url)
        if form is None:
            raise RuntimeError("No se encontró el formulario CAS de autenticación.")

        payload = form.to_payload(username=username, password=password)
        response = self.session.post(
            form.action,
            data=payload,
            allow_redirects=True,
            timeout=self.timeout,
        )
        return response

    @staticmethod
    def is_cas_login_page(url: str, html: str) -> bool:
        normalized = url.lower()
        if "/cas/login" in normalized:
            return True
        html_lower = html.lower()
        return "central authentication service" in html_lower or "powered by apereo cas" in html_lower

    @staticmethod
    def extract_login_form(html: str, base_url: str) -> LoginForm | None:
        parser = CasLoginParser()
        parser.feed(html)

        if not parser.forms:
            return None

        for form in parser.forms:
            has_username = any(item.name == "username" for item in form.inputs)
            has_password = any(item.name == "password" for item in form.inputs)
            if has_username and has_password:
                form.action = urljoin(base_url, form.action)
                return form

        fallback = parser.forms[0]
        fallback.action = urljoin(base_url, fallback.action)
        return fallback

    @staticmethod
    def extract_candidate_urls(html: str, base_url: str) -> list[str]:
        patterns = [
            r"""(?:href|src|action|data-url)\s*=\s*["']([^"']+)["']""",
            r"""fetch\(\s*["']([^"']+)["']""",
            r"""(?:get|post|ajax)\s*\(\s*["']([^"']+)["']""",
        ]
        found: set[str] = set()
        for pattern in patterns:
            for match in re.findall(pattern, html, flags=re.IGNORECASE):
                absolute = urljoin(base_url, match.strip())
                parsed = urlparse(absolute)
                if parsed.scheme in {"http", "https"}:
                    found.add(absolute)
        return sorted(found)[:40]


def save_text(path: str | None, content: str) -> None:
    if not path:
        return
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")


def load_cookies(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"No existe el archivo de cookies: {file_path}")
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("El archivo de cookies no contiene un objeto JSON valido.")
    return {str(key): str(value) for key, value in data.items()}


def summarize_response(
    response: requests.Response,
    origin_url: str,
    session: requests.Session,
) -> dict[str, object]:
    client = EgoBedocCasClient()
    return {
        "origin_url": origin_url,
        "final_url": response.url,
        "status_code": response.status_code,
        "authenticated": "/cas/login" not in response.url.lower(),
        "cookie_names": sorted(session.cookies.get_dict().keys()),
        "redirect_chain": [item.url for item in response.history] + [response.url],
        "candidate_urls": client.extract_candidate_urls(response.text, response.url),
        "content_snippet": clean_text_snippet(response.text),
    }


def clean_text_snippet(html: str, limit: int = 900) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cliente base para conectar eGOB/e-Bedoc mediante CAS.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspecciona el flujo CAS sin autenticarse.")
    inspect_parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="Ruta protegida a inspeccionar.")
    inspect_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    inspect_parser.add_argument("--save-html", help="Guarda el HTML recibido en disco.")
    inspect_parser.add_argument("--insecure", action="store_true", help="Desactiva la verificación TLS para certificados internos.")

    login_parser = subparsers.add_parser("login", help="Inicia sesión en CAS y descarga una ruta protegida.")
    login_parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="Ruta protegida a abrir luego del login.")
    login_parser.add_argument("--path", help="Ruta adicional a consultar después del login, por ejemplo /my/passig_citizen.")
    login_parser.add_argument("--username", default=os.getenv("EGOBEDOC_USERNAME"), help="Usuario CAS.")
    login_parser.add_argument("--password", default=os.getenv("EGOBEDOC_PASSWORD"), help="Clave CAS.")
    login_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    login_parser.add_argument("--save-html", help="Guarda el HTML final en disco.")
    login_parser.add_argument("--save-cookies", help="Guarda las cookies activas en un JSON.")
    login_parser.add_argument("--insecure", action="store_true", help="Desactiva la verificación TLS para certificados internos.")

    login_parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="No solicitar usuario o clave de manera interactiva si faltan.",
    )

    fetch_parser = subparsers.add_parser("fetch", help="Consulta una ruta autenticada usando cookies guardadas.")
    fetch_parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="Ruta protegida base.")
    fetch_parser.add_argument("--path", required=True, help="Ruta autenticada adicional, por ejemplo /issues/1191961.")
    fetch_parser.add_argument("--cookies-file", required=True, help="JSON de cookies guardado con el comando login.")
    fetch_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    fetch_parser.add_argument("--save-html", help="Guarda el HTML final en disco.")
    fetch_parser.add_argument("--insecure", action="store_true", help="Desactiva la verificaciÃ³n TLS para certificados internos.")

    return parser


def resolve_credentials(
    username: str | None,
    password: str | None,
    *,
    interactive: bool,
) -> tuple[str, str]:
    resolved_username = (username or "").strip()
    resolved_password = password or ""

    if interactive and not resolved_username:
        try:
            resolved_username = input("Usuario CAS: ").strip()
        except EOFError:
            resolved_username = ""

    if interactive and not resolved_password:
        try:
            resolved_password = getpass.getpass("Clave CAS: ")
        except EOFError:
            resolved_password = ""

    return resolved_username, resolved_password


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    client = EgoBedocCasClient(timeout=args.timeout, verify=not getattr(args, "insecure", False))
    try:
        if args.command == "inspect":
            info = client.inspect_login(args.origin)
            if args.save_html:
                response = client.fetch_entrypoint(args.origin)
                save_text(args.save_html, response.text)
            print(json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "login":
            username, password = resolve_credentials(
                args.username,
                args.password,
                interactive=not args.no_prompt,
            )
            if not username or not password:
                parser.error("Para el comando login debes proporcionar --username y --password o usar EGOBEDOC_USERNAME/EGOBEDOC_PASSWORD.")

            response = client.login(args.origin, username, password)
            if args.path:
                target_url = urljoin(args.origin, args.path)
                response = client.session.get(target_url, allow_redirects=True, timeout=args.timeout)

            if args.save_html:
                save_text(args.save_html, response.text)

            if args.save_cookies:
                cookies_path = Path(args.save_cookies)
                cookies_path.parent.mkdir(parents=True, exist_ok=True)
                cookies_path.write_text(
                    json.dumps(client.session.cookies.get_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            print(
                json.dumps(
                    summarize_response(response, args.origin, client.session),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            if "/cas/login" in response.url.lower():
                return 2
            return 0

        if args.command == "fetch":
            cookies = load_cookies(args.cookies_file)
            client.session.cookies.update(cookies)
            target_url = urljoin(args.origin, args.path)
            response = client.session.get(target_url, allow_redirects=True, timeout=args.timeout)

            if args.save_html:
                save_text(args.save_html, response.text)

            print(
                json.dumps(
                    summarize_response(response, args.origin, client.session),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            if "/cas/login" in response.url.lower():
                return 2
            return 0
    except requests.RequestException as error:
        print(
            json.dumps(
                {
                    "error": "network_error",
                    "message": str(error),
                    "hint": (
                        "No se pudo abrir el portal desde este runtime. "
                        "En algunos equipos el navegador sí accede, pero Python puede quedar bloqueado "
                        "por firewall, antivirus o reglas de salida HTTPS. "
                        "Si el portal usa un certificado interno, prueba también con --insecure."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3

    parser.error("Comando no soportado.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
